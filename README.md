# SchoolPulse Bot (Импульс школы)

**SchoolPulse Bot** — чат-бот для платформы **MAX** (VK Group), который автоматизирует управление школьными мероприятиями и уведомлениями. Бот позволяет представителям школ получать актуальные уведомления о событиях, организаторам — создавать и публиковать анонсы, а администраторам — модерировать пользователей.

Проект написан на **Python 3.11** + **FastAPI** + **PostgreSQL** (asyncpg + SQLAlchemy 2.0 asyncio) и предназначен для развёртывания через Docker.

---

## Роли

| Роль | Описание | Основные возможности |
|------|----------|---------------------|
| **Представитель школы** (`School_Representative`) | Регистрируется, получает уведомления, ставит отметки о прочтении | Просмотр списка мероприятий, настройка уведомлений |
| **Организатор** (`Organizer`) | Создаёт и редактирует посты о мероприятиях | Управление событиями, просмотр аналитики |
| **Администратор** (`Admin`) | Модерирует пользователей, верифицирует роли | Управление ролями, блокировка, верификация |

---

## Структура проекта

```
SchoolPulseBot/
├── app/
│   ├── main.py              # Точка входа FastAPI / Long Polling
│   ├── config.py            # Конфигурация (pydantic-settings)
│   ├── models/              # SQLAlchemy модели
│   │   ├── user.py
│   │   ├── event.py
│   │   └── notification.py
│   ├── routers/
│   │   └── webhook.py       # POST /webhook — приём событий от MAX
│   └── services/
│       ├── max_api.py       # MAX API Client
│       ├── auth.py          # Авторизация и роли
│       ├── webhook.py       # Управление подписками
│       └── ...
├── db/
│   └── database.py          # Async SQLAlchemy engine + session
├── Dockerfile               # Многостадийная сборка образа
├── docker-compose.yml       # app + PostgreSQL
├── .env.example             # Шаблон переменных окружения
├── requirements.txt
└── README.md
```

---

## Быстрый старт (Docker)

### 1. Клонирование

```bash
git clone https://github.com/EgorSetup/SchoolPulseBot.git
cd SchoolPulseBot
```

### 2. Настройка окружения

Скопируйте и отредактируйте `.env`:

```bash
cp .env.example .env
```

Минимально необходимые переменные:

| Переменная | Значение по умолчанию | Обязательная |
|-----------|----------------------|:------------:|
| `MAX_BOT_TOKEN` | — | ✅ |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/school_pulse_bot` | ❌ |
| `WEBHOOK_URL` | `https://your-domain.com/webhook` | ❌ |
| `WEBHOOK_SECRET` | — | ❌ |

> В `docker-compose.yml` строка подключения к БД формируется автоматически из переменных `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — их тоже можно переопределить в `.env`.

### 3. Запуск

```bash
docker compose up -d
```

После запуска:

- FastAPI приложение доступно на `http://localhost:8000`
- Health check: `GET /health`
- PostgreSQL слушает на порту `5432`

### 4. Подписка на вебхук (один раз)

```bash
docker compose exec app python -m app.main --subscribe
```

---

## Запуск без Docker (для разработки)

```bash
# Виртуальное окружение
python -m venv .venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate  # Linux / Mac

# Зависимости
pip install -r requirements.txt

# Настроить .env
cp .env.example .env
# Отредактировать MAX_BOT_TOKEN, DATABASE_URL и т.д.

# Создать таблицы
python -c "
import asyncio
from db.database import engine
from app.models import Base
asyncio.run(Base.metadata.create_all(engine))
"

# Запустить сервер (Webhook — production)
python -m app.main

# Long Polling (только разработка)
python -m app.main --long-polling
```

---

## API

Полная документация по API платформы MAX: **[https://dev.max.ru/docs-api](https://dev.max.ru/docs-api)**

### Используемые методы MAX API

| Метод | URL | Назначение |
|-------|-----|-----------|
| `GET /me` | Информация о боте | Проверка токена |
| `POST /messages` | Отправка сообщений | Ответы пользователям |
| `POST /subscriptions` | Подписка на Webhook | Получение событий |
| `DELETE /subscriptions` | Отписка | Остановка вебхука |
| `POST /answers` | Ответ на callback | Обработка нажатий кнопок |
| `GET /updates` | Long Polling | Dev-режим |

### Webhook события

- `bot_started` — пользователь запустил бота
- `bot_added` — бот добавлен в чат / канал
- `message_created` — новое сообщение
- `message_callback` — нажатие на inline-кнопку
- `message_edited` / `message_removed` — редактирование / удаление
- `dialog_removed` / `bot_stopped` — остановка бота

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `MAX_BOT_TOKEN` | — | Токен бота MAX (обязательный) |
| `MAX_API_BASE` | `https://platform-api.max.ru` | Базовый URL MAX API |
| `WEBHOOK_URL` | `https://your-domain.com/webhook` | Публичный URL для вебхука |
| `WEBHOOK_SECRET` | — | Секрет для верификации вебхуков |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/school_pulse_bot` | Строка подключения к БД |
| `HOST` | `0.0.0.0` | Хост для сервера |
| `PORT` | `8000` | Порт для сервера |
| `LOG_LEVEL` | `INFO` | Уровень логирования |

---

## Требования

- Python 3.11+
- PostgreSQL 15+
- Docker & Docker Compose (для развёртывания)
- MAX Bot Token (получить на [business.max.ru](https://business.max.ru/self))
- HTTPS-сертификат для продакшн-вебхука

---

## Лицензия

MIT
