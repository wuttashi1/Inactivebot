<div align="center">

# Activity Manager

Telegram-бот для управления активностью участников групп: отчёты, предупреждения и очистка неактивных участников.

[Правила разработки](CONTRIBUTING.md) · [Ветки](https://github.com/wuttashi1/Inactivebot/branches)

</div>

---

## Возможности

- Панель управления группами и доступом администраторов.
- Учёт активности, отчёты и предупреждения.
- Синхронизация участников и задачи по расписанию.
- Хранение данных в PostgreSQL через SQLAlchemy.

## Запуск через Docker

Создайте `.env` в корне репозитория:

```dotenv
BOT_TOKEN=replace_with_your_token
OWNER_ID=123456789
DATABASE_URL=postgresql+asyncpg://activity:activity@db:5432/activity_bot
```

```bash
docker compose up -d --build
docker compose logs -f bot
```

Это конфигурация для локального запуска с параметрами базы из `docker-compose.yml`. Для сервера задайте собственный пароль и согласуйте его с `DATABASE_URL`. Добавьте бота администратором в группу и откройте `/start` в личном чате.

## Навигация

- `bot/handlers/` — команды и панели.
- `bot/services/` — отчёты, предупреждения, синхронизация и очистка.
- `bot/database/` — модели и запросы.
- `bot/scheduler/` — фоновые задачи.

## Разработка

Соглашения по веткам и изменениям: [CONTRIBUTING.md](CONTRIBUTING.md).
