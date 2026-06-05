# SchoolPulse Bot

Чат-бот для платформы MAX (VK Group) для управления школьными мероприятиями и уведомлениями.

## Архитектура

```
SchoolPulseBot/
├── app/
│   ├── __init__.py
│   ├── main.py              # Точка входа FastAPI / Long Polling
│   ├── config.py            # Конфигурация из переменных окружения
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py          # User, SchoolRepresentative, Organizer, Admin
│   │   ├── event.py         # Event
│   │   └── notification.py  # Notification, ReadReceipt
│   ├── services/
│   │   ├── __init__.py
│   │   ├── max_api.py       # MAX API Client (send, subscribe, etc.)
│   │   ├── auth.py          # Разрешение и управление ролями
│   │   └── webhook.py       # Управление подписками вебхуков
│   └── routers/
│       ├── __init__.py
│       └── webhook.py       # POST /webhook — приём событий
├── db/
│   ├── __init__.py
│   └── database.py          # Async SQLAlchemy engine + session
├── .env.example
├── requirements.txt
└── README.md
```

## Роли

| Роль | Описание | Права |
|------|----------|-------|
| **School_Representative** | Регистрация, получение уведомлений, отметки о прочтении | Чтение уведомлений о мероприятиях |
| **Organizer** | Создание/редактирование постов, аналитика | Управление мероприятиями, просмотр статистики |
| **Admin** | Модерация аккаунтов, верификация ролей | Управление пользователями, верификация |

## База данных (PostgreSQL)

```
users
├── max_id (PK) — ID пользователя MAX
├── username
├── role (enum: school_representative, organizer, admin)
├── is_verified
└── created_at / updated_at

school_representatives  → FK(users.max_id) — расширенный профиль представителя
    ├── school_name
    ├── school_class
    └── notification_preferences (JSON)

organizers              → FK(users.max_id) — расширенный профиль организатора
    ├── organization
    └── created_events_count

admins                  → FK(users.max_id) — расширенный профиль администратора
    ├── can_verify
    └── can_moderate

events
├── title, description
├── organizer_id → FK(users.max_id)
├── scheduled_at
└── created_at

notifications
├── event_id → FK(events.id)
├── text
└── sent_at

read_receipts
├── user_id → FK(users.max_id)
├── notification_id → FK(notifications.id)
└── read_at
```

## Установка и запуск

```bash
# Клонировать
git clone <repo>
cd SchoolPulseBot

# Виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Зависимости
pip install -r requirements.txt

# Настроить .env
cp .env.example .env
# Отредактировать .env: MAX_BOT_TOKEN, DATABASE_URL и т.д.

# Создать таблицы (один раз)
python -c "
import asyncio
from db.database import engine
from app.models import Base
asyncio.run(Base.metadata.create_all(engine))
"

# Запустить сервер (Webhook — production)
python -m app.main

# Или Long Polling (только для разработки)
python -m app.main --long-polling

# Подписаться на события вебхука
python -m app.main --subscribe
```

## API MAX (используемые методы)

| Метод | URL | Назначение |
|-------|-----|-----------|
| `GET /me` | Информация о боте | Проверка токена |
| `POST /messages` | Отправка сообщений | Ответы пользователям |
| `POST /subscriptions` | Подписка на Webhook | Получение событий |
| `DELETE /subscriptions` | Отписка | Остановка вебхука |
| `POST /answers` | Ответ на callback | Обработка нажатий кнопок |
| `GET /updates` | Long Polling | Dev-режим |

## Webhook события

- `bot_started` — пользователь запустил бота
- `bot_added` — бот добавлен в чат/канал
- `message_created` — новое сообщение
- `message_callback` — нажатие на inline-кнопку
- `message_edited` / `message_removed` — редактирование/удаление
- `dialog_removed` / `bot_stopped` — остановка бота

## Требования

- Python 3.11+
- PostgreSQL 15+
- MAX Bot Token (получить на [business.max.ru](https://business.max.ru/self))
- HTTPS-сертификат для продакшн-вебхука
