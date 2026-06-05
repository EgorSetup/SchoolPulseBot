"""
Webhook endpoint — receives updates from MAX API.
All event types are handled here and dispatched to the appropriate services.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from app.models.user import UserRole
from app.services.auth import resolve_user_role, get_user_by_id
from app.services.max_api import (
    send_message,
    answer_callback,
    verify_webhook_secret,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _build_buttons(buttons: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Helper to build inline_keyboard attachment."""
    return [
        {
            "type": "inline_keyboard",
            "payload": {"buttons": buttons},
        }
    ]


async def _greet_new_user(max_id: int, session: AsyncSession) -> None:
    """Send a welcome message with role-based menu."""
    user, is_new = await resolve_user_role(session, max_id)
    role_label = user.role.value.replace("_", " ").title()

    text = (
        f"👋 Добро пожаловать в SchoolPulse!\n"
        f"Ваша роль: *{role_label}*\n"
        f"{'✅ Аккаунт верифицирован' if user.is_verified else '⏳ Ожидает верификации администратором'}\n\n"
    )

    if user.role == UserRole.school_representative:
        text += "Вы будете получать уведомления о школьных мероприятиях."
        buttons = _build_buttons([
            [{"type": "callback", "text": "📋 Мои уведомления", "payload": "my_notifications"}],
            [{"type": "callback", "text": "✅ Отметить прочитанным", "payload": "mark_read"}],
        ])
    elif user.role == UserRole.organizer:
        text += "Вы можете создавать и редактировать посты о мероприятиях."
        buttons = _build_buttons([
            [{"type": "callback", "text": "✏️ Создать мероприятие", "payload": "create_event"}],
            [{"type": "callback", "text": "📊 Аналитика", "payload": "analytics"}],
        ])
    elif user.role == UserRole.admin:
        text += "Вам доступна модерация аккаунтов и верификация ролей."
        buttons = _build_buttons([
            [{"type": "callback", "text": "👥 Управление пользователями", "payload": "manage_users"}],
            [{"type": "callback", "text": "✅ Верификация", "payload": "verify_users"}],
        ])
    else:
        buttons = []

    await send_message(text, user_id=max_id, attachments=buttons or None, format_="markdown")


async def process_update(update: dict[str, Any], session: AsyncSession) -> None:
    """
    Process a single MAX API update (used by both webhook and long-polling).
    Mutates nothing, sends messages via MAX API.
    """
    update_type: str = update.get("update_type", "")
    logger.info("Processing update: %s", update_type)

    if update_type == "bot_started":
        user_id = update["user"]["user_id"]
        username = update["user"].get("username")
        await resolve_user_role(session, user_id, username=username)
        await _greet_new_user(user_id, session)

    elif update_type == "bot_added":
        logger.info(
            "Bot added to chat %s (channel=%s)",
            update.get("chat_id"),
            update.get("is_channel"),
        )

    elif update_type == "message_created":
        sender = update.get("message", {}).get("sender")
        if sender is None:
            return

        user_id = sender["user_id"]
        text = update.get("message", {}).get("body", {}).get("text", "")

        user, _ = await resolve_user_role(
            session, user_id, username=sender.get("username")
        )

        text_lower = text.strip().lower()
        if text_lower in ("/start", "начать", "меню"):
            await _greet_new_user(user_id, session)
        elif text_lower == "моя роль":
            role_label = user.role.value.replace("_", " ").title()
            await send_message(
                f"Ваша роль: *{role_label}*\n"
                f"{'✅ Верифицирован' if user.is_verified else '⏳ Не верифицирован'}",
                user_id=user_id,
                format_="markdown",
            )
        else:
            await send_message(
                f"Сообщение получено. Ваш ID: `{user_id}`, роль: `{user.role.value}`",
                user_id=user_id,
                format_="markdown",
            )

    elif update_type == "message_callback":
        user_id = update["user"]["user_id"]
        callback_id = update["message_callback"]["callback_id"]
        payload = update["message_callback"]["payload"]

        await resolve_user_role(session, user_id)
        user = await get_user_by_id(session, user_id)

        if payload == "my_notifications":
            await send_message(
                "📋 *Ваши уведомления*\n\nЗдесь будут отображаться уведомления о мероприятиях.",
                user_id=user_id,
                format_="markdown",
            )
        elif payload == "mark_read":
            await send_message(
                "✅ Отметка о прочтении будет реализована в следующем обновлении.",
                user_id=user_id,
            )
        elif payload == "create_event":
            if user and user.role != UserRole.organizer:
                await send_message("❌ Только организаторы могут создавать мероприятия.", user_id=user_id)
            else:
                await send_message(
                    "✏️ *Создание мероприятия*\n\n"
                    "Отправьте мне название мероприятия, дату и описание в формате:\n"
                    "`Название | ДД.ММ.ГГГГ | Описание`",
                    user_id=user_id,
                    format_="markdown",
                )
        elif payload == "analytics":
            if user and user.role != UserRole.organizer:
                await send_message("❌ Только организаторы имеют доступ к аналитике.", user_id=user_id)
            else:
                await send_message(
                    "📊 *Аналитика вовлеченности*\n\nСтатистика будет доступна после создания мероприятий.",
                    user_id=user_id,
                    format_="markdown",
                )
        elif payload in ("manage_users", "verify_users"):
            if user and user.role != UserRole.admin:
                await send_message("❌ Только администраторы имеют доступ к управлению пользователями.", user_id=user_id)
            else:
                await send_message("👥 Функция управления пользователями будет реализована в следующем обновлении.", user_id=user_id)
        else:
            logger.debug("Unknown callback payload: %s from user %s", payload, user_id)

        await answer_callback(callback_id)

    elif update_type in ("message_edited", "message_removed"):
        logger.debug("Passive event: %s (chat=%s)", update_type, update.get("chat_id"))

    elif update_type in ("dialog_removed", "bot_stopped"):
        user_id = update.get("user", {}).get("user_id")
        if user_id:
            logger.info("User %s stopped/removed bot", user_id)

    else:
        logger.debug("Unhandled update_type: %s", update_type)


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
