<div align="center">

# Activity Manager

Telegram group activity manager with reports, inactivity warnings, member synchronization and scheduled cleanup.

[Contributing](CONTRIBUTING.md) · [Branches](https://github.com/wuttashi1/Inactivebot/branches)

</div>

---

## Features

- Group management and administrator access controls.
- Activity tracking, reports and inactivity warnings.
- Member synchronization and scheduled tasks.
- PostgreSQL storage through SQLAlchemy.

## Run with Docker

Create a local `.env` in the repository root:

```dotenv
BOT_TOKEN=replace_with_your_token
OWNER_ID=123456789
DATABASE_URL=postgresql+asyncpg://activity:activity@db:5432/activity_bot
```

```bash
docker compose up -d --build
docker compose logs -f bot
```

These database settings match the local Compose configuration. For deployment, choose your own database password and update `DATABASE_URL` accordingly. Add the bot to your group as an administrator and open `/start` in a private chat.

## Project layout

- `bot/handlers/` — commands and panels.
- `bot/services/` — reports, warnings, synchronization and cleanup.
- `bot/database/` — models and queries.
- `bot/scheduler/` — background jobs.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch and contribution guidelines.
