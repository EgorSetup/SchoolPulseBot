"""
Keyboard factory — builds inline keyboards for the MAX Bot API.

This module is purely compositional: it returns attachment payloads
that can be passed to send_message() or answer_callback().
No business logic, no database calls.
"""

from __future__ import annotations

from typing import Any


def _inline_keyboard(buttons: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Wrap a button layout into an inline_keyboard attachment."""
    return [
        {
            "type": "inline_keyboard",
            "payload": {"buttons": buttons},
        }
    ]


def _callback_button(text: str, payload: str) -> dict[str, Any]:
    return {"type": "callback", "text": text, "payload": payload}


def _message_button(text: str, payload: str) -> dict[str, Any]:
    return {"type": "message", "text": text, "payload": payload}


def _link_button(text: str, url: str) -> dict[str, Any]:
    return {"type": "link", "text": text, "url": url}


# ---- Public keyboard presets ---- #


def main_menu(is_admin: bool = False, is_organizer: bool = False) -> list[dict[str, Any]]:
    """
    Main menu shown to every user after registration / /start.

    Buttons:
      - Мои уведомления  (callback)
      - Регистрация на событие (callback)
      - Профиль (callback)
      - [📅 Управление событиями] (only if is_organizer)
      - [🛠 Админ-панель] (only if is_admin)
    """
    rows: list[list[dict[str, Any]]] = [
        [
            _callback_button("📋 Мои уведомления", "my_notifications"),
            _callback_button("📝 Регистрация на событие", "register_event"),
        ],
        [
            _callback_button("👤 Профиль", "profile"),
        ],
    ]
    if is_organizer:
        rows.append([
            _callback_button("📅 Управление событиями", "org_create_event"),
        ])
    if is_admin:
        rows.append([
            _callback_button("🛠 Админ-панель", "admin_main_menu"),
        ])
    return _inline_keyboard(rows)


def profile_menu(is_verified: bool, has_school_data: bool) -> list[dict[str, Any]]:
    """
    Profile sub-menu.

    Args:
        is_verified: whether the user account is verified.
        has_school_data: whether school+class is already filled in.
    """
    rows: list[list[dict[str, Any]]] = []

    if not is_verified:
        rows.append([_callback_button("🏫 Указать школу и класс", "set_school")])

    if has_school_data:
        rows.append([_callback_button("✏️ Изменить школу/класс", "set_school")])

    rows.append([_callback_button("🔙 Назад", "main_menu")])

    return _inline_keyboard(rows)


def school_confirmation(school: str, school_class: str) -> list[dict[str, Any]]:
    """Confirmation keyboard after user typed school / class."""
    return _inline_keyboard([
        [
            _callback_button("✅ Да, верно", "confirm_school"),
            _callback_button("🔄 Ввести заново", "set_school"),
        ],
        [_callback_button("🔙 Назад", "main_menu")],
    ])


def notification_actions() -> list[dict[str, Any]]:
    """Actions available on the notifications screen."""
    return _inline_keyboard([
        [
            _callback_button("✅ Отметить всё прочитанным", "mark_all_read"),
        ],
        [_callback_button("🔙 Назад", "main_menu")],
    ])


# ═══════════════════════════════════════════════════════
#  Organizer keyboards
# ═══════════════════════════════════════════════════════


def organizer_main_menu() -> list[dict[str, Any]]:
    """
    Main menu for Organizer users.

    Buttons:
      - Создать событие
      - Мои события
      - Аналитика
      - Профиль
    """
    return _inline_keyboard([
        [
            _callback_button("📅 Создать событие", "org_create_event"),
            _callback_button("📋 Мои события", "org_my_events"),
        ],
        [
            _callback_button("📊 Аналитика", "org_analytics"),
            _callback_button("👤 Профиль", "profile"),
        ],
    ])


def event_actions(event_id: int) -> list[dict[str, Any]]:
    """
    Actions available after an event is created or viewed.

    Args:
        event_id: the event ID to include in the callback payload.
    """
    return _inline_keyboard([
        [
            _callback_button(
                "📨 Разослать участникам",
                f"org_send_notification:{event_id}",
            ),
        ],
        [
            _callback_button(
                "📊 Статистика события",
                f"org_event_stats:{event_id}",
            ),
        ],
        [
            _callback_button("🔙 В меню", "org_main_menu"),
        ],
    ])


def notification_ack_keyboard(
    notification_id: int,
) -> list[dict[str, Any]]:
    """
    Keyboard attached to a notification message, allowing the recipient
    to acknowledge reading it.

    The payload encodes the notification_id so we can record the read receipt.
    """
    return _inline_keyboard([
        [
            _callback_button(
                "✅ Ознакомлен",
                f"ack:{notification_id}",
            ),
        ],
    ])


def broadcast_completed(event_id: int) -> list[dict[str, Any]]:
    """Shown after a broadcast finishes."""
    return _inline_keyboard([
        [
            _callback_button(
                "📊 Аналитика",
                f"org_event_stats:{event_id}",
            ),
        ],
        [
            _callback_button("🔙 В меню", "org_main_menu"),
        ],
    ])


def analytics_menu() -> list[dict[str, Any]]:
    """Options on the analytics dashboard."""
    return _inline_keyboard([
        [
            _callback_button("🔄 Обновить", "org_analytics"),
        ],
        [
            _callback_button("🔙 В меню", "org_main_menu"),
        ],
    ])


# ═══════════════════════════════════════════════════════
#  Event registration keyboards (for SchoolRepresentative)
# ═══════════════════════════════════════════════════════


def event_registration_list(events: list[tuple[int, str, str]]) -> list[dict[str, Any]]:
    """
    Inline keyboard listing events available for registration.

    Each button shows the event title and carries the event id in payload.

    Args:
        events: list of (event_id, title, date_str) tuples.
    """
    rows: list[list[dict[str, Any]]] = []
    for event_id, title, date_str in events:
        # Truncate long titles to fit on a button
        display_title = title if len(title) <= 40 else title[:37] + "..."
        rows.append([
            _callback_button(
                f"📅 {display_title} ({date_str})",
                f"ev_select:{event_id}",
            ),
        ])
    rows.append([_callback_button("🔙 Назад", "main_menu")])
    return _inline_keyboard(rows)


def event_detail_actions(event_id: int, is_registered: bool = False) -> list[dict[str, Any]]:
    """
    Keyboard shown after viewing event details.

    Args:
        event_id: the event ID.
        is_registered: whether the user is already registered.
    """
    rows: list[list[dict[str, Any]]] = []
    if is_registered:
        rows.append([_callback_button("✅ Уже записан", f"ev_already:{event_id}")])
    else:
        rows.append([_callback_button("📝 Подтвердить участие", f"ev_confirm:{event_id}")])
    rows.append([_callback_button("🔙 К списку событий", "register_event")])
    return _inline_keyboard(rows)


# ═══════════════════════════════════════════════════════
#  Admin keyboards
# ═══════════════════════════════════════════════════════


def admin_main_menu() -> list[dict[str, Any]]:
    """
    Main menu for Admin users.

    Buttons:
      - Заявки на верификацию
      - Управление пользователями
      - Панель мониторинга
      - Логи действий
      - Профиль
    """
    return _inline_keyboard([
        [
            _callback_button("✅ Заявки на верификацию", "admin_verification:1"),
            _callback_button("👥 Управление пользователями", "admin_user_mgmt"),
        ],
        [
            _callback_button("📊 Панель мониторинга", "admin_dashboard"),
            _callback_button("📋 Логи действий", "admin_logs"),
        ],
        [
            _callback_button("👤 Профиль", "profile"),
        ],
    ])


def admin_verification_keyboard(
    current_page: int,
    total_pages: int,
    user_id: int,
) -> list[dict[str, Any]]:
    """
    Keyboard for a single verification request (approve/reject).
    """
    return _inline_keyboard([
        [
            _callback_button("✅ Одобрить", f"admin_approve:{user_id}:{current_page}"),
            _callback_button("❌ Отклонить", f"admin_reject:{user_id}:{current_page}"),
        ],
        [
            _callback_button("🔙 К списку заявок", f"admin_verification:{current_page}"),
        ],
        [
            _callback_button("🏠 Главное меню", "admin_main_menu"),
        ],
    ])


def admin_verification_list_keyboard(
    current_page: int,
    total_pages: int,
) -> list[dict[str, Any]]:
    """
    Pagination keyboard for the verification queue list.
    Shows page numbers + back to main menu.
    """
    rows: list[list[dict[str, Any]]] = []

    # Pagination row
    page_buttons: list[dict[str, Any]] = []
    if total_pages > 1:
        if current_page > 1:
            page_buttons.append(
                _callback_button("⬅️", f"admin_verification:{current_page - 1}")
            )
        page_buttons.append(
            _callback_button(f"📄 {current_page}/{total_pages}", "admin_verification:0")
        )
        if current_page < total_pages:
            page_buttons.append(
                _callback_button("➡️", f"admin_verification:{current_page + 1}")
            )
        rows.append(page_buttons)

    rows.append([_callback_button("🏠 Главное меню", "admin_main_menu")])
    return _inline_keyboard(rows)


def admin_user_mgmt_keyboard() -> list[dict[str, Any]]:
    """User management menu."""
    return _inline_keyboard([
        [
            _callback_button("🔍 Поиск по ID", "admin_search_user"),
        ],
        [
            _callback_button("📋 Все пользователи", "admin_list_users:1"),
        ],
        [
            _callback_button("🔙 Назад", "admin_main_menu"),
        ],
    ])


def admin_user_role_keyboard(
    target_max_id: int,
) -> list[dict[str, Any]]:
    """Pick a role to assign to a user."""
    return _inline_keyboard([
        [
            _callback_button("👤 School Rep", f"admin_set_role:{target_max_id}:school_representative"),
            _callback_button("🎫 Organizer", f"admin_set_role:{target_max_id}:organizer"),
        ],
        [
            _callback_button("🛡️ Admin", f"admin_set_role:{target_max_id}:admin"),
        ],
        [
            _callback_button("🔙 Назад", "admin_user_mgmt"),
        ],
    ])


def admin_users_list_keyboard(
    users: list[tuple[int, str | None, str]],
    current_page: int,
    total_pages: int,
) -> list[dict[str, Any]]:
    """
    Paginated list of users for the admin to pick from.
    Each user gets a button showing their ID + role.
    """
    rows: list[list[dict[str, Any]]] = []

    # First 4 users max per page of buttons (to avoid overflow)
    for max_id, username, role in users[:4]:
        label = f"#{max_id}"
        if username:
            label += f" {username}"
        label += f" ({role})"
        rows.append([
            _callback_button(label, f"admin_set_role:{max_id}:role_picker"),
        ])

    # Pagination
    page_buttons: list[dict[str, Any]] = []
    if total_pages > 1:
        if current_page > 1:
            page_buttons.append(
                _callback_button("⬅️", f"admin_list_users:{current_page - 1}")
            )
        page_buttons.append(_callback_button(f"📄 {current_page}/{total_pages}", "admin_main_menu"))
        if current_page < total_pages:
            page_buttons.append(
                _callback_button("➡️", f"admin_list_users:{current_page + 1}")
            )
        rows.append(page_buttons)

    rows.append([_callback_button("🔙 Назад", "admin_user_mgmt")])
    return _inline_keyboard(rows)


def admin_dashboard_keyboard() -> list[dict[str, Any]]:
    """Dashboard refresh and back buttons."""
    return _inline_keyboard([
        [
            _callback_button("🔄 Обновить", "admin_dashboard"),
        ],
        [
            _callback_button("🏠 Главное меню", "admin_main_menu"),
        ],
    ])


def admin_logs_keyboard() -> list[dict[str, Any]]:
    """Back button from logs view."""
    return _inline_keyboard([
        [
            _callback_button("🔄 Обновить", "admin_logs"),
        ],
        [
            _callback_button("🏠 Главное меню", "admin_main_menu"),
        ],
    ])
