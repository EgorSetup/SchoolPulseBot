"""
Webhook endpoint — receives updates from MAX API.
All event types are handled here and dispatched to the appropriate services.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from app.models.user import User, UserRole
from app.services.auth import (
    is_guest_needing_profile,
    is_ready_school_representative,
    resolve_user_role,
)
from app.services.keyboard_service import (
    admin_dashboard_keyboard,
    admin_logs_keyboard,
    admin_main_menu,
    admin_user_mgmt_keyboard,
    admin_user_role_keyboard,
    admin_users_list_keyboard,
    admin_verification_keyboard,
    admin_verification_list_keyboard,
    analytics_menu,
    broadcast_completed,
    event_actions,
    main_menu,
    notification_ack_keyboard,
    notification_actions,
    organizer_main_menu,
    profile_menu,
    school_confirmation,
)
from app.services.school_representative_service import (
    get_profile as get_school_profile,
    has_complete_profile,
    save_school,
    save_school_class,
)
from app.services.event_service import (
    create_event,
    get_event_by_id,
    get_organizer_events,
    get_organizer_profile,
)
from app.services.notification_service import (
    get_recipients,
    record_read_receipt,
    send_broadcast,
    get_last_notification_for_user,
)
from app.services.analytics_service import (
    get_analytics_overview,
    get_event_analytics_list,
)
from app.services.admin_service import (
    get_system_dashboard,
    get_verification_queue,
    get_admin_logs,
    search_users,
    verify_user,
    reject_user,
    set_user_role as admin_set_user_role,
)
from app.services.auth import require_admin
from app.services.max_api import (
    send_message,
    answer_callback,
    verify_webhook_secret,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

# ────────────────────────────────────────────────────
#  In-memory dialog state tracking
#  (maps max_id -> state name, persisted per request)
# ────────────────────────────────────────────────────

DIALOG_STATE_KEY = "_dialog_state"

# Allowed dialog states
STATE_NONE = ""
STATE_AWAITING_SCHOOL = "awaiting_school"
STATE_AWAITING_CLASS = "awaiting_class"
STATE_AWAITING_CONFIRM = "awaiting_confirm"
# Organizer event creation states
STATE_AWAITING_EVENT_TITLE = "awaiting_event_title"
STATE_AWAITING_EVENT_DESCRIPTION = "awaiting_event_description"
STATE_AWAITING_EVENT_DATE = "awaiting_event_date"


def _get_dialog_state(user: User) -> str:
    """Read dialog state stored on the user object."""
    return getattr(user, DIALOG_STATE_KEY, STATE_NONE)


def _set_dialog_state(user: User, state: str) -> None:
    """Store dialog state temporarily on the user object."""
    setattr(user, DIALOG_STATE_KEY, state)


# ────────────────────────────────────────────────────
#  Welcome & menu helpers
# ────────────────────────────────────────────────────


async def _send_welcome(user_id: int, is_new: bool = False) -> None:
    """
    Send the initial welcome message.
    - New / unregistered users get a message asking them to specify school & class.
    - Registered users see the main menu.
    """
    if is_new:
        text = (
            "👋 *Привет! Я бот «Импульс школы».*\n\n"
            "Чтобы начать пользоваться, укажи свою школу и класс.\n"
            "Напиши название своей школы."
        )
    else:
        text = (
            "👋 *Добро пожаловать в «Импульс школы»!*\n\n"
            "Выбери действие в меню ниже:"
        )

    await send_message(
        text,
        user_id=user_id,
        attachments=main_menu(),
        format_="markdown",
    )


async def _send_menu(user_id: int, user_role: UserRole | None = None) -> None:
    """Resend the appropriate menu based on user role."""
    if user_role == UserRole.organizer:
        await send_message(
            "📌 *Меню организатора*\n\nВыбери действие:",
            user_id=user_id,
            attachments=organizer_main_menu(),
            format_="markdown",
        )
    elif user_role == UserRole.admin:
        await send_message(
            "🛡️ *Административная панель*\n\nВыбери действие:",
            user_id=user_id,
            attachments=admin_main_menu(),
            format_="markdown",
        )
    else:
        await send_message(
            "📌 *Главное меню*\n\nВыбери действие:",
            user_id=user_id,
            attachments=main_menu(),
            format_="markdown",
        )


async def _send_profile(user: User, session: AsyncSession) -> None:
    """Show the profile screen."""
    has_school = await has_complete_profile(session, user.max_id)
    profile = await get_school_profile(session, user.max_id)

    lines = [
        "👤 *Твой профиль*\n",
        f"*Роль:* {user.role.value}",
        f"*Статус:* {'✅ Верифицирован' if user.is_verified else '⏳ Не верифицирован'}",
    ]

    if user.role == UserRole.organizer:
        org_profile = await get_organizer_profile(session, user.max_id)
        if org_profile:
            lines.append(f"*Организация:* {org_profile.organization}")
            lines.append(f"*Создано событий:* {org_profile.created_events_count}")
    elif profile:
        if profile.school_name:
            lines.append(f"*Школа:* {profile.school_name}")
        if profile.school_class:
            lines.append(f"*Класс:* {profile.school_class}")

    if not user.is_verified and not has_school:
        lines.append("")
        lines.append("📝 *Чтобы завершить регистрацию, укажи школу и класс.*")

    await send_message(
        "\n".join(lines),
        user_id=user.max_id,
        attachments=profile_menu(is_verified=user.is_verified, has_school_data=has_school),
        format_="markdown",
    )


# ────────────────────────────────────────────────────
#  School registration dialog
# ────────────────────────────────────────────────────


async def _handle_school_dialog_step(
    user: User,
    session: AsyncSession,
    text: str,
    callback_id: str | None = None,
) -> None:
    """
    Handle the multi-step dialog for setting school name and class.
    """
    state = _get_dialog_state(user)

    if state == STATE_NONE:
        _set_dialog_state(user, STATE_AWAITING_SCHOOL)
        await send_message(
            "🏫 *Укажи название своей школы*\n\n"
            "Например: *МБОУ СОШ № 15*",
            user_id=user.max_id,
            format_="markdown",
        )

    elif state == STATE_AWAITING_SCHOOL:
        _set_dialog_state(user, STATE_AWAITING_CLASS)
        await save_school(session, user.max_id, text)
        await send_message(
            f"✅ Школа *{text.strip()}* сохранена!\n\n"
            "Теперь укажи свой класс (или напиши «—», если не нужно):\n"
            "Например: *9А* или *11Б*",
            user_id=user.max_id,
            format_="markdown",
        )

    elif state == STATE_AWAITING_CLASS:
        class_value = text.strip()
        if class_value in ("—", "-", "нет", ""):
            class_value = ""

        await save_school_class(session, user.max_id, class_value)
        _set_dialog_state(user, STATE_AWAITING_CONFIRM)

        profile = await get_school_profile(session, user.max_id)
        school_name = profile.school_name if profile else "?"
        school_class = profile.school_class if profile and profile.school_class else "не указан"

        await send_message(
            f"📋 *Проверь данные:*\n\n"
            f"🏫 Школа: *{school_name}*\n"
            f"👥 Класс: *{school_class}*\n\n"
            "Всё верно?",
            user_id=user.max_id,
            attachments=school_confirmation(school_name, school_class),
            format_="markdown",
        )

    if callback_id:
        await answer_callback(callback_id)


async def _finalize_school_registration(user: User, session: AsyncSession) -> None:
    """Finalize the school registration."""
    _set_dialog_state(user, STATE_NONE)
    user.is_verified = True
    await session.flush()

    profile = await get_school_profile(session, user.max_id)
    school_name = profile.school_name if profile else "?"
    school_class = profile.school_class if profile and profile.school_class else "не указан"

    # Determine which menu to show
    is_organizer = user.role == UserRole.organizer
    menu = organizer_main_menu() if is_organizer else main_menu()

    await send_message(
        f"🎉 *Регистрация завершена!*\n\n"
        f"Твои данные:\n"
        f"🏫 Школа: *{school_name}*\n"
        f"👥 Класс: *{school_class}*\n\n"
        f"Теперь ты можешь пользоваться ботом! 👇",
        user_id=user.max_id,
        attachments=menu,
        format_="markdown",
    )


# ────────────────────────────────────────────────────
#  Organizer — Event creation dialog
# ────────────────────────────────────────────────────


async def _handle_org_event_dialog_step(
    user: User,
    session: AsyncSession,
    text: str,
    callback_id: str | None = None,
) -> None:
    """
    Multi-step event creation wizard:
      1. Ask for title
      2. Ask for description
      3. Ask for date (DD.MM.YYYY or YYYY-MM-DD)
      4. Create event and show actions
    """
    state = _get_dialog_state(user)

    if state == STATE_NONE or state == "awaiting_event_title":
        # Step 1: title received → ask for description
        _set_dialog_state(user, STATE_AWAITING_EVENT_DESCRIPTION)
        setattr(user, "_event_title", text.strip())

        await send_message(
            "📝 *Введи описание события*\n\n"
            "Опиши, о чём это событие. Можно просто отправить «—», если описания не нужно.",
            user_id=user.max_id,
            format_="markdown",
        )

    elif state == STATE_AWAITING_EVENT_DESCRIPTION:
        # Step 2: description received → ask for date
        _set_dialog_state(user, STATE_AWAITING_EVENT_DATE)
        description = text.strip()
        setattr(
            user, "_event_description",
            description if description not in ("—", "-", "") else None,
        )

        await send_message(
            "📅 *Введи дату события*\n\n"
            "Формат: *ДД.ММ.ГГГГ* (например, 25.12.2026)\n"
            "Или: *ГГГГ-ММ-ДД* (например, 2026-12-25)",
            user_id=user.max_id,
            format_="markdown",
        )

    elif state == STATE_AWAITING_EVENT_DATE:
        # Step 3: date received → create event
        _set_dialog_state(user, STATE_NONE)

        title = getattr(user, "_event_title", "Без названия")
        description = getattr(user, "_event_description", None)

        # Parse date
        parsed_date = _parse_date(text.strip())
        if parsed_date is None:
            await send_message(
                "❌ *Неверный формат даты.*\n\n"
                "Пожалуйста, используй *ДД.ММ.ГГГГ* (например, 25.12.2026)\n"
                "Или *ГГГГ-ММ-ДД* (например, 2026-12-25)",
                user_id=user.max_id,
                format_="markdown",
            )
            # Re-ask
            _set_dialog_state(user, STATE_AWAITING_EVENT_DATE)
            return

        # Validate date is in the future
        if parsed_date < datetime.utcnow():
            await send_message(
                "⚠️ *Дата в прошлом!*\n\n"
                "Пожалуйста, укажи будущую дату.",
                user_id=user.max_id,
                format_="markdown",
            )
            return

        try:
            event = await create_event(
                session,
                organizer_id=user.max_id,
                title=title,
                description=description,
                scheduled_at=parsed_date,
            )

            date_str = parsed_date.strftime("%d.%m.%Y")
            await send_message(
                f"✅ *Событие создано!*\n\n"
                f"📅 *Название:* {title}\n"
                f"📝 *Описание:* {description or '—'}\n"
                f"📆 *Дата:* {date_str}\n\n"
                "Что хочешь сделать дальше?",
                user_id=user.max_id,
                attachments=event_actions(event.id),
                format_="markdown",
            )

            # Clean up temp state
            _clean_event_state(user)

        except Exception as exc:
            logger.exception("Failed to create event: %s", exc)
            await send_message(
                "❌ *Ошибка при создании события.* Попробуй ещё раз.",
                user_id=user.max_id,
            )
            _set_dialog_state(user, STATE_NONE)
            _clean_event_state(user)

    if callback_id:
        await answer_callback(callback_id)


def _parse_date(text: str) -> Optional[datetime]:
    """Try to parse a date string in DD.MM.YYYY or YYYY-MM-DD format."""
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _clean_event_state(user: User) -> None:
    """Remove temporary event creation state from user object."""
    if hasattr(user, "_event_title"):
        delattr(user, "_event_title")
    if hasattr(user, "_event_description"):
        delattr(user, "_event_description")


# ────────────────────────────────────────────────────
#  Organizer — Send notification flow
# ────────────────────────────────────────────────────


async def _handle_send_notification(
    user: User,
    session: AsyncSession,
    event_id: int,
    callback_id: str | None = None,
) -> None:
    """
    Handle the "Send notification" action for an event.

    1. Fetch the event (ensure it belongs to this organizer).
    2. Get all eligible recipients (verified SchoolRepresentatives).
    3. Ask organizer to confirm with optional filters.
    4. Send broadcast.
    """
    event = await get_event_by_id(session, event_id)
    if event is None:
        await send_message(
            "❌ *Событие не найдено.*",
            user_id=user.max_id,
        )
        return

    if event.organizer_id != user.max_id:
        await send_message(
            "❌ *Это не твоё событие.*",
            user_id=user.max_id,
        )
        return

    if not event.notifications:
        # First notification for this event: ask if we should send to everyone
        # or filter
        recipients = await get_recipients(session)
        if not recipients:
            await send_message(
                "⚠️ *Нет получателей.*\n\n"
                "В системе пока нет зарегистрированных представителей школ.",
                user_id=user.max_id,
            )
            return

        # Build notification text based on event data
        date_str = event.scheduled_at.strftime("%d.%m.%Y")
        notification_text = (
            f"📢 *Новое мероприятие!*\n\n"
            f"📅 *{event.title}*\n"
            f"📝 {event.description or 'Описание не указано'}\n"
            f"📆 *Дата:* {date_str}\n\n"
            f"Нажми «✅ Ознакомлен», чтобы подтвердить получение."
        )

        # Store in user temp state
        setattr(user, "_send_event_id", event.id)
        setattr(user, "_send_text", notification_text)
        setattr(user, "_recipient_count", len(recipients))

        await send_message(
            f"📨 *Подготовка рассылки*\n\n"
            f"Событие: *{event.title}*\n"
            f"Получателей: *{len(recipients)}*\n\n"
            f"Отправить всем представителям школ?",
            user_id=user.max_id,
            attachments=(
                _confirm_send_keyboard(event.id)
            ),
            format_="markdown",
        )
    else:
        # Already has notifications: resend
        last_notif = event.notifications[-1]
        recipients = await get_recipients(session)
        setattr(user, "_send_event_id", event.id)
        setattr(user, "_send_text", last_notif.text)

        await send_message(
            f"📨 *Повторная рассылка*\n\n"
            f"Событие: *{event.title}*\n"
            f"Текст будет взят из предыдущего уведомления.\n"
            f"Получателей: *{len(recipients)}*\n\n"
            f"Отправить?",
            user_id=user.max_id,
            attachments=(_confirm_send_keyboard(event.id)),
            format_="markdown",
        )

    if callback_id:
        await answer_callback(callback_id)


def _confirm_send_keyboard(event_id: int) -> list[dict[str, Any]]:
    """Keyboard for confirming notification send."""
    from app.services.keyboard_service import _inline_keyboard, _callback_button

    return _inline_keyboard([
        [
            _callback_button("✅ Отправить всем", f"org_do_send:{event_id}"),
        ],
        [
            _callback_button("🔙 В меню", "org_main_menu"),
        ],
    ])


async def _execute_broadcast(
    user: User,
    session: AsyncSession,
    event_id: int,
    callback_id: str | None = None,
) -> None:
    """
    Actually execute the broadcast.
    """
    event = await get_event_by_id(session, event_id)
    if event is None:
        await send_message(
            "❌ *Событие не найдено.*",
            user_id=user.max_id,
        )
        return

    # Get recipients (all verified SchoolRepresentatives for now)
    recipients = await get_recipients(session)
    if not recipients:
        await send_message(
            "⚠️ *Нет получателей для рассылки.*",
            user_id=user.max_id,
        )
        return

    recipient_ids = [r.user_id for r in recipients]

    # Use stored text or build from event
    text = getattr(user, "_send_text", None)
    if text is None:
        date_str = event.scheduled_at.strftime("%d.%m.%Y")
        text = (
            f"📢 *Новое мероприятие!*\n\n"
            f"📅 *{event.title}*\n"
            f"📝 {event.description or 'Описание не указано'}\n"
            f"📆 *Дата:* {date_str}\n\n"
            f"Нажми «✅ Ознакомлен», чтобы подтвердить получение."
        )

    # Send progress message
    await send_message(
        f"⏳ *Начинаю рассылку...*\n"
        f"Всего получателей: {len(recipient_ids)}\n"
        f"Ожидай завершения...",
        user_id=user.max_id,
    )

    try:
        notification = await send_broadcast(
            session,
            event_id=event_id,
            text=text,
            recipient_ids=recipient_ids,
        )

        # Flush the sent status to the recipient records
        await session.flush()

        sent_count = sum(
            1 for r in notification.recipients if r.sent
        )
        error_count = sum(
            1 for r in notification.recipients if not r.sent
        )

        await send_message(
            f"✅ *Рассылка завершена!*\n\n"
            f"📨 Уведомление #{notification.id}\n"
            f"✅ Отправлено: *{sent_count}*\n"
            f"❌ Ошибок: *{error_count}*\n"
            f"📊 Всего получателей: *{len(recipient_ids)}*",
            user_id=user.max_id,
            attachments=broadcast_completed(event_id),
            format_="markdown",
        )

        # Clean up temp state
        if hasattr(user, "_send_text"):
            delattr(user, "_send_text")
        if hasattr(user, "_send_event_id"):
            delattr(user, "_send_event_id")

    except Exception as exc:
        logger.exception("Broadcast failed: %s", exc)
        await send_message(
            f"❌ *Ошибка при рассылке:* {exc}",
            user_id=user.max_id,
        )

    if callback_id:
        await answer_callback(callback_id)


# ────────────────────────────────────────────────────
#  Organizer — Analytics
# ────────────────────────────────────────────────────


async def _show_analytics(
    user: User,
    session: AsyncSession,
    callback_id: str | None = None,
) -> None:
    """Show the analytics dashboard for the organizer."""
    overview = await get_analytics_overview(session, user.max_id)

    lines = [
        "📊 *Панель аналитики*\n",
        f"📅 *Всего событий:* {overview.event_count}",
        f"📨 *Всего отправлено уведомлений:* {overview.total_sent}",
        f"✅ *Подтверждено прочтений:* {overview.total_read}",
        f"📈 *Конверсия:* {overview.conversion_rate}%",
    ]

    # Per-event breakdown
    if overview.event_count > 0:
        events_analytics = await get_event_analytics_list(session, user.max_id)
        lines.append("\n───────────────\n*По событиям:*\n")
        for ea in events_analytics:
            lines.append(
                f"📅 *{ea.event_title}* — "
                f"отправлено: {ea.sent_count}, "
                f"прочитано: {ea.read_count}, "
                f"кнв.: {ea.conversion_rate}%"
            )

    await send_message(
        "\n".join(lines),
        user_id=user.max_id,
        attachments=analytics_menu(),
        format_="markdown",
    )

    if callback_id:
        await answer_callback(callback_id)


# ────────────────────────────────────────────────────
#  Organizer — My events list
# ────────────────────────────────────────────────────


async def _show_my_events(
    user: User,
    session: AsyncSession,
    callback_id: str | None = None,
) -> None:
    """Show all events created by this organizer."""
    events = await get_organizer_events(session, user.max_id)

    if not events:
        await send_message(
            "📋 *У тебя пока нет событий.*\n\n"
            "Создай новое событие через меню!",
            user_id=user.max_id,
            attachments=organizer_main_menu(),
            format_="markdown",
        )
        return

    # Show last 5 events with actions
    lines = ["📋 *Мои события*\n"]
    for ev in events[:5]:
        lines.append(
            f"📅 *{ev.title}*\n"
            f"📆 {ev.scheduled_at.strftime('%d.%m.%Y')}\n"
        )

    if len(events) > 5:
        lines.append(f"*...и ещё {len(events) - 5} событий*")

    await send_message(
        "\n".join(lines),
        user_id=user.max_id,
        attachments=organizer_main_menu(),
        format_="markdown",
    )

    if callback_id:
        await answer_callback(callback_id)


# ────────────────────────────────────────────────────
#  Event stats per event
# ────────────────────────────────────────────────────


async def _show_event_stats(
    user: User,
    session: AsyncSession,
    event_id: int,
    callback_id: str | None = None,
) -> None:
    """Show statistics for a specific event."""
    event = await get_event_by_id(session, event_id)
    if event is None:
        await send_message(
            "❌ *Событие не найдено.*",
            user_id=user.max_id,
        )
        return

    # Get analytics for this event
    events_list = await get_event_analytics_list(session, user.max_id)
    event_an = next((ea for ea in events_list if ea.event_id == event_id), None)

    lines = [
        f"📊 *Статистика события*\n",
        f"📅 *{event.title}*\n",
    ]

    if event_an:
        lines.append(f"📨 Отправлено: *{event_an.sent_count}*")
        lines.append(f"✅ Прочитано: *{event_an.read_count}*")
        lines.append(f"📈 Конверсия: *{event_an.conversion_rate}%*")
    else:
        lines.append("📨 *Ещё не было рассылок*")

    await send_message(
        "\n".join(lines),
        user_id=user.max_id,
        attachments=event_actions(event_id),
        format_="markdown",
    )

    if callback_id:
        await answer_callback(callback_id)


# ────────────────────────────────────────────────────
#  Read receipt handler (acknowledgement)
# ────────────────────────────────────────────────────


async def _handle_ack(
    user: User,
    session: AsyncSession,
    notification_id: int,
) -> None:
    """
    Handle a recipient clicking "Ознакомлен" on a notification.

    Records a read receipt and thanks the user.
    """
    try:
        is_new = await record_read_receipt(
            session,
            user_id=user.max_id,
            notification_id=notification_id,
        )

        if is_new:
            await send_message(
                "✅ *Спасибо!* Твоё ознакомление зафиксировано.",
                user_id=user.max_id,
            )
        else:
            await send_message(
                "📌 Ты уже подтвердил ознакомление с этим уведомлением.",
                user_id=user.max_id,
            )

    except Exception as exc:
        logger.exception("Failed to record read receipt: %s", exc)
        await send_message(
            "❌ Произошла ошибка при записи ознакомления.",
            user_id=user.max_id,
        )


# ────────────────────────────────────────────────────
#  Update dispatcher
# ────────────────────────────────────────────────────


async def process_update(update: dict[str, Any], session: AsyncSession) -> None:
    """
    Process a single MAX API update (used by both webhook and long-polling).
    """
    update_type: str = update.get("update_type", "")
    logger.info("Processing update: %s", update_type)

    if update_type == "bot_started":
        user_id = update["user"]["user_id"]
        username = update["user"].get("username")
        user, is_new = await resolve_user_role(session, user_id, username=username)

        if is_new:
            await _send_welcome(user_id, is_new=True)
        else:
            await _send_welcome(user_id, is_new=False)

    elif update_type == "bot_added":
        logger.info(
            "Bot added to chat %s (channel=%s)",
            update.get("chat_id"),
            update.get("is_channel"),
        )

    elif update_type == "message_created":
        await _handle_message_created(update, session)

    elif update_type == "message_callback":
        await _handle_message_callback(update, session)

    elif update_type in ("message_edited", "message_removed"):
        logger.debug("Passive event: %s (chat=%s)", update_type, update.get("chat_id"))

    elif update_type in ("dialog_removed", "bot_stopped"):
        user_id = update.get("user", {}).get("user_id")
        if user_id:
            logger.info("User %s stopped/removed bot", user_id)

    else:
        logger.debug("Unhandled update_type: %s", update_type)


# ────────────────────────────────────────────────────
#  message_created handler
# ────────────────────────────────────────────────────


async def _handle_message_created(
    update: dict[str, Any],
    session: AsyncSession,
) -> None:
    """Handle incoming text messages from users."""
    sender = update.get("message", {}).get("sender")
    if sender is None:
        return

    user_id = sender["user_id"]
    body = update.get("message", {}).get("body", {}) or {}
    text = body.get("text", "").strip()

    user, _ = await resolve_user_role(session, user_id, username=sender.get("username"))

    # ── Dialog / registration flow ──
    state = _get_dialog_state(user)
    if state in (
        STATE_AWAITING_SCHOOL,
        STATE_AWAITING_CLASS,
    ):
        await _handle_school_dialog_step(user, session, text)
        return

    # Organizer event creation dialogs
    if state in (
        STATE_AWAITING_EVENT_TITLE,
        STATE_AWAITING_EVENT_DESCRIPTION,
        STATE_AWAITING_EVENT_DATE,
    ):
        await _handle_org_event_dialog_step(user, session, text)
        return

    # ── Admin: search user by ID dialog ──
    if state == "awaiting_admin_user_search":
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён.", user_id=user_id)
            return
        _set_dialog_state(user, STATE_NONE)

        if text.isdigit():
            target_max_id = int(text)
            # Show the user with role-pick buttons
            target_user_data, _ = await search_users(session, query=text)
            if target_user_data:
                target_u = target_user_data[0]
                await send_message(
                    f"👤 *Пользователь #{target_u.max_id}*\n"
                    f"*Имя:* {target_u.username or '—'}\n"
                    f"*Роль:* {target_u.role.value}\n"
                    f"*Статус:* {'✅ Верифицирован' if target_u.is_verified else '⏳ Не верифицирован'}\n\n"
                    "Выбери действие:",
                    user_id=user_id,
                    attachments=admin_user_role_keyboard(target_max_id),
                    format_="markdown",
                )
            else:
                await send_message(
                    f"❌ *Пользователь #{target_max_id} не найден.*",
                    user_id=user_id,
                    attachments=admin_user_mgmt_keyboard(),
                )
        else:
            await send_message(
                "❌ *Неверный формат.* Пожалуйста, введи числовой ID пользователя.",
                user_id=user_id,
                attachments=admin_user_mgmt_keyboard(),
            )
        return

    # ── Commands ──
    text_lower = text.lower()

    if text_lower in ("/start", "начать", "меню", "главное меню"):
        # Determine role-specific menu
        menu_role = user.role if user.role in (UserRole.organizer, UserRole.admin) else None
        await _send_menu(user_id, user_role=menu_role)

    elif text_lower in ("/profile", "профиль", "👤 профиль"):
        await _send_profile(user, session)

    elif text_lower in ("/регистрация", "/register"):
        await _handle_school_dialog_step(user, session, text)

    else:
        guest = await is_guest_needing_profile(session, user_id)
        ready = await is_ready_school_representative(session, user_id)

        if guest:
            await send_message(
                "👋 Привет! Чтобы начать пользоваться ботом, укажи свою школу и класс.\n"
                "Нажми «👤 Профиль» в меню или напиши /регистрация.",
                user_id=user_id,
                attachments=main_menu(),
            )
        elif ready:
            await send_message(
                f"✅ Сообщение получено, {user.username or 'пользователь'}!\n"
                f"Твои данные школы подтверждены.",
                user_id=user_id,
            )
        else:
            await send_message(
                f"✉️ Сообщение получено. Используй /меню для навигации.",
                user_id=user_id,
            )


# ══════════════════════════════════════════════════════
#  Admin panel handler functions
# ══════════════════════════════════════════════════════


async def _admin_show_verification_queue(
    user: User,
    session: AsyncSession,
    page: int = 1,
) -> None:
    """Show the paginated list of unverified users."""
    PAGE_SIZE = 10
    users, total = await get_verification_queue(
        session, page=page, page_size=PAGE_SIZE,
    )
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    if not users:
        await send_message(
            "✅ *Все заявки обработаны!*\n\n"
            "Нет пользователей, ожидающих верификации.",
            user_id=user.max_id,
            attachments=admin_main_menu(),
            format_="markdown",
        )
        return

    lines = [f"📋 *Заявки на верификацию* (стр. {page}/{total_pages})\n"]
    for u in users:
        username = u.username or "—"
        created = u.created_at.strftime("%d.%m.%Y %H:%M")
        lines.append(
            f"👤 #{u.max_id} | {username}\n"
            f"   📅 {created} | {u.role.value}\n"
        )

    await send_message(
        "\n".join(lines),
        user_id=user.max_id,
        attachments=admin_verification_list_keyboard(page, total_pages),
        format_="markdown",
    )


async def _admin_show_single_verification(
    user: User,
    session: AsyncSession,
    target_max_id: int,
    page: int,
) -> None:
    """Show a single unverified user with approve/reject buttons."""
    from app.services.auth import get_user_by_id

    target = await get_user_by_id(session, target_max_id)
    if target is None:
        await send_message(
            "❌ *Пользователь не найден.*",
            user_id=user.max_id,
            attachments=admin_main_menu(),
        )
        return

    username = target.username or "—"
    created = target.created_at.strftime("%d.%m.%Y %H:%M")
    text = (
        f"👤 *Пользователь #{target.max_id}*\n\n"
        f"*Имя:* {username}\n"
        f"*Роль:* {target.role.value}\n"
        f"*Статус:* ⏳ Ожидает верификации\n"
        f"*Зарегистрирован:* {created}\n\n"
        "Одобрить или отклонить заявку?"
    )
    await send_message(
        text,
        user_id=user.max_id,
        attachments=admin_verification_keyboard(page, 1, target_max_id),
        format_="markdown",
    )


async def _admin_approve_user(
    user: User,
    session: AsyncSession,
    target_max_id: int,
    page: int,
) -> None:
    """Approve a user's verification."""
    updated = await verify_user(
        session, admin_id=user.max_id, target_max_id=target_max_id,
    )
    if updated:
        await send_message(
            f"✅ *Пользователь #{target_max_id} верифицирован!*",
            user_id=user.max_id,
        )
    else:
        await send_message(
            "❌ *Пользователь не найден.*",
            user_id=user.max_id,
        )

    # Return to queue
    await _admin_show_verification_queue(user, session, page)


async def _admin_reject_user(
    user: User,
    session: AsyncSession,
    target_max_id: int,
    page: int,
) -> None:
    """Reject (delete) a user from the system."""
    success = await reject_user(
        session, admin_id=user.max_id, target_max_id=target_max_id,
    )
    if success:
        await send_message(
            f"🗑️ *Пользователь #{target_max_id} отклонён и удалён из системы.*",
            user_id=user.max_id,
        )
    else:
        await send_message(
            "❌ *Пользователь не найден.*",
            user_id=user.max_id,
        )

    # Return to queue
    await _admin_show_verification_queue(user, session, page)


async def _admin_show_dashboard(
    user: User,
    session: AsyncSession,
) -> None:
    """Show the global system dashboard."""
    stats = await get_system_dashboard(session)
    text = (
        "📊 *Глобальная панель мониторинга*\n\n"
        f"👥 *Всего пользователей:* {stats.total_users}\n"
        f"   ├ ✅ Верифицировано: {stats.total_verified_users}\n"
        f"   ├ 🎫 Организаторов: {stats.total_organizers}\n"
        f"   └ 🛡️ Администраторов: {stats.total_admins}\n\n"
        f"🏫 *Активных школ:* {stats.total_active_schools}\n"
        f"📅 *Всего событий:* {stats.total_events}\n"
        f"📆 *Событий за неделю:* {stats.events_this_week}\n"
    )
    await send_message(
        text,
        user_id=user.max_id,
        attachments=admin_dashboard_keyboard(),
        format_="markdown",
    )


async def _admin_show_logs(
    user: User,
    session: AsyncSession,
) -> None:
    """Show the most recent admin action logs."""
    logs = await get_admin_logs(session, limit=20)
    if not logs:
        await send_message(
            "📋 *Логи действий*\n\n"
            "Пока нет записей.",
            user_id=user.max_id,
            attachments=admin_logs_keyboard(),
            format_="markdown",
        )
        return

    lines = ["📋 *Последние действия администраторов*\n"]
    for log in logs:
        ts = log.created_at.strftime("%d.%m %H:%M")
        lines.append(
            f"[{ts}] admin #{log.admin_id}: *{log.action}*"
            + (f" → {log.target_id}" if log.target_id else "")
        )
        if log.details:
            # Truncate long details
            detail = log.details[:80] + "…" if len(log.details) > 80 else log.details
            lines.append(f"   └ {detail}")

    await send_message(
        "\n".join(lines),
        user_id=user.max_id,
        attachments=admin_logs_keyboard(),
        format_="markdown",
    )


async def _admin_list_users(
    user: User,
    session: AsyncSession,
    page: int = 1,
) -> None:
    """Show a paginated list of all users."""
    PAGE_SIZE = 10
    users_list, total = await search_users(
        session, query="", page=page, page_size=PAGE_SIZE,
    )
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    if not users_list:
        await send_message(
            "📋 *В системе пока нет пользователей.*",
            user_id=user.max_id,
            attachments=admin_user_mgmt_keyboard(),
        )
        return

    lines = [f"👥 *Все пользователи* (стр. {page}/{total_pages}, всего {total})\n"]
    for u in users_list:
        username = u.username or "—"
        verified = "✅" if u.is_verified else "⏳"
        lines.append(f"{verified} #{u.max_id} | {username} | {u.role.value}")

    # Prepare user tuples for the keyboard
    user_tuples = [
        (u.max_id, u.username, u.role.value) for u in users_list[:4]
    ]

    await send_message(
        "\n".join(lines),
        user_id=user.max_id,
        attachments=admin_users_list_keyboard(user_tuples, page, total_pages),
        format_="markdown",
    )


# ────────────────────────────────────────────────────
#  message_callback handler
# ────────────────────────────────────────────────────


async def _handle_message_callback(
    update: dict[str, Any],
    session: AsyncSession,
) -> None:
    """
    Handle inline keyboard button presses (callback_query).
    Always calls answer_callback() first to give instant feedback,
    THEN processes the action.
    """
    user_id = update["user"]["user_id"]
    callback_data = update.get("message_callback", {})
    callback_id: str = callback_data["callback_id"]
    payload: str = callback_data.get("payload", "")

    user, _ = await resolve_user_role(session, user_id)

    # ── Answer callback immediately so the MAX UI stops showing a spinner ──
    await answer_callback(callback_id)

    logger.debug("Callback from user %d: %s", user_id, payload)

    # ── Read receipt acknowledgement ──
    if payload.startswith("ack:"):
        notification_id_str = payload.split(":", 1)[1]
        try:
            notification_id = int(notification_id_str)
            await _handle_ack(user, session, notification_id)
        except ValueError:
            logger.warning("Invalid notification_id in ack payload: %s", payload)
        return

    # ── Organizer: Main menu ──
    if payload == "org_main_menu":
        await _send_menu(user_id, user_role=UserRole.organizer)

    # ── Organizer: Create event ──
    elif payload == "org_create_event":
        _set_dialog_state(user, STATE_AWAITING_EVENT_TITLE)
        await send_message(
            "📅 *Создание нового события*\n\n"
            "Введи *название* события:",
            user_id=user_id,
            format_="markdown",
        )

    # ── Organizer: My events list ──
    elif payload == "org_my_events":
        await _show_my_events(user, session)

    # ── Organizer: Analytics dashboard ──
    elif payload == "org_analytics":
        await _show_analytics(user, session)

    # ── Organizer: Send notification (prepare) ──
    elif payload.startswith("org_send_notification:"):
        event_id_str = payload.split(":", 1)[1]
        try:
            event_id = int(event_id_str)
            await _handle_send_notification(user, session, event_id)
        except ValueError:
            logger.warning("Invalid event_id in send_notification payload: %s", payload)

    # ── Organizer: Execute broadcast ──
    elif payload.startswith("org_do_send:"):
        event_id_str = payload.split(":", 1)[1]
        try:
            event_id = int(event_id_str)
            await _execute_broadcast(user, session, event_id)
        except ValueError:
            logger.warning("Invalid event_id in do_send payload: %s", payload)

    # ── Organizer: Event statistics ──
    elif payload.startswith("org_event_stats:"):
        event_id_str = payload.split(":", 1)[1]
        try:
            event_id = int(event_id_str)
            await _show_event_stats(user, session, event_id)
        except ValueError:
            logger.warning("Invalid event_id in event_stats payload: %s", payload)

    # ── Existing callbacks ──
    elif payload == "main_menu":
        await _send_menu(user_id)

    elif payload == "my_notifications":
        await send_message(
            "*📋 Мои уведомления*\n\n"
            "Здесь будут отображаться уведомления о новых мероприятиях твоей школы.",
            user_id=user_id,
            attachments=notification_actions(),
            format_="markdown",
        )

    elif payload == "mark_all_read":
        await send_message(
            "✅ Все уведомления отмечены как прочитанные.", user_id=user_id
        )

    elif payload == "register_event":
        await send_message(
            "*📝 Регистрация на событие*\n\n"
            "Функция будет доступна в ближайших обновлениях. "
            "Следи за уведомлениями!",
            user_id=user_id,
            format_="markdown",
        )

    elif payload == "profile":
        await _send_profile(user, session)

    elif payload == "set_school":
        _set_dialog_state(user, STATE_AWAITING_SCHOOL)
        await send_message(
            "🏫 *Укажи название своей школы*\n\n"
            "Например: *МБОУ СОШ № 15*\n"
            "Или нажми «🔙 Назад», чтобы вернуться в меню.",
            user_id=user_id,
            format_="markdown",
        )

    elif payload == "confirm_school":
        await _finalize_school_registration(user, session)

    # ══════════════════════════════════════════════════
    #  Admin callbacks
    # ══════════════════════════════════════════════════

    elif payload == "admin_main_menu":
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён. Требуется роль Admin.", user_id=user_id)
            return
        await send_message(
            "🛡️ *Административная панель*\n\nВыбери действие:",
            user_id=user_id,
            attachments=admin_main_menu(),
            format_="markdown",
        )

    # ── Verification queue ──
    elif payload.startswith("admin_verification:"):
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён.", user_id=user_id)
            return
        parts = payload.split(":", 1)
        page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        if page < 1:
            page = 1
        await _admin_show_verification_queue(user, session, page)

    # ── Approve user ──
    elif payload.startswith("admin_approve:"):
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён.", user_id=user_id)
            return
        parts = payload.split(":")
        if len(parts) >= 2:
            target_id = int(parts[1])
            page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            await _admin_approve_user(user, session, target_id, page)

    # ── Reject user ──
    elif payload.startswith("admin_reject:"):
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён.", user_id=user_id)
            return
        parts = payload.split(":")
        if len(parts) >= 2:
            target_id = int(parts[1])
            page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            await _admin_reject_user(user, session, target_id, page)

    # ── Dashboard ──
    elif payload == "admin_dashboard":
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён.", user_id=user_id)
            return
        await _admin_show_dashboard(user, session)

    # ── Admin logs ──
    elif payload == "admin_logs":
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён.", user_id=user_id)
            return
        await _admin_show_logs(user, session)

    # ── User management menu ──
    elif payload == "admin_user_mgmt":
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён.", user_id=user_id)
            return
        await send_message(
            "👥 *Управление пользователями*\n\n"
            "Найди пользователя по ID или просмотри всех.",
            user_id=user_id,
            attachments=admin_user_mgmt_keyboard(),
            format_="markdown",
        )

    # ── Search user by ID ──
    elif payload == "admin_search_user":
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён.", user_id=user_id)
            return
        _set_dialog_state(user, "awaiting_admin_user_search")
        await send_message(
            "🔍 *Поиск пользователя*\n\n"
            "Введи ID пользователя (число) для поиска:",
            user_id=user_id,
            format_="markdown",
        )

    # ── List all users (paginated) ──
    elif payload.startswith("admin_list_users:"):
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён.", user_id=user_id)
            return
        parts = payload.split(":", 1)
        page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        await _admin_list_users(user, session, page)

    # ── Set role (role picker for a user) ──
    elif payload.startswith("admin_set_role:"):
        if not await require_admin(session, user.max_id):
            await send_message("⛔ Доступ запрещён.", user_id=user_id)
            return
        parts = payload.split(":")
        if len(parts) >= 2:
            target_max_id = int(parts[1])
            sub_action = parts[2] if len(parts) > 2 else "role_picker"
            if sub_action == "role_picker":
                # Show role selection keyboard
                target_user = await search_users(session, query=str(target_max_id))
                target_user_obj = target_user[0][0] if target_user[0] else None
                username_str = target_user_obj.username if target_user_obj else "?"
                await send_message(
                    f"👤 *Пользователь #{target_max_id}* ({username_str})\n\n"
                    "Выбери новую роль:",
                    user_id=user_id,
                    attachments=admin_user_role_keyboard(target_max_id),
                    format_="markdown",
                )
            else:
                # Actually set the role
                try:
                    new_role = UserRole(sub_action)
                except ValueError:
                    await send_message("❌ *Неизвестная роль.*", user_id=user_id)
                    return
                updated = await admin_set_user_role(
                    session, admin_id=user.max_id,
                    target_max_id=target_max_id,
                    new_role=new_role,
                )
                if updated:
                    await send_message(
                        f"✅ *Роль пользователя #{target_max_id} изменена на* "
                        f"*{new_role.value}*",
                        user_id=user_id,
                        attachments=admin_user_mgmt_keyboard(),
                        format_="markdown",
                    )
                else:
                    await send_message(
                        "❌ *Пользователь не найден.*",
                        user_id=user_id,
                    )

    else:
        logger.debug("Unknown callback payload: %s from user %s", payload, user_id)


# ────────────────────────────────────────────────────
#  FastAPI endpoint
# ────────────────────────────────────────────────────


@router.post("")
async def handle_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_max_secret: str | None = Header(None, alias="X-Max-Bot-Api-Secret"),
) -> dict[str, str]:
    """
    Main webhook handler for incoming MAX API updates.
    Returns {"status": "ok"} on success.
    """
    if not verify_webhook_secret(x_max_secret):
        logger.warning("Webhook secret mismatch — rejecting request")
        return {"status": "error", "message": "invalid secret"}

    update: dict[str, Any] = await request.json()
    update_type: str = update.get("update_type", "")
    logger.info("Received webhook update: %s", update_type)

    try:
        await process_update(update, session)
    except Exception:
        logger.exception("Error processing webhook update: %s", update_type)

    return {"status": "ok"}
