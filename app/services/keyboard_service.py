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


def main_menu() -> list[dict[str, Any]]:
    """
    Main menu shown to every user after registration / /start.

    Buttons:
      - Мои уведомления  (callback)
      - Регистрация на событие (callback)
      - Профиль (callback)
    """
    return _inline_keyboard([
        [
            _callback_button("📋 Мои уведомления", "my_notifications"),
            _callback_button("📝 Регистрация на событие", "register_event"),
        ],
        [
            _callback_button("👤 Профиль", "profile"),
        ],
    ])


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
