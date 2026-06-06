import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.database import init_db
from bot.handlers import setup_routers
from bot.handlers.commands import setup_bot_commands
from bot.logging_setup import setup_logging
from bot.middleware.admin import AdminContextMiddleware
from bot.scheduler import setup_scheduler

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    await init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(AdminContextMiddleware())
    dp.include_router(setup_routers())

    await setup_bot_commands(bot)

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Bot started")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "callback_query",
                "my_chat_member",
                "chat_member",
                "message_reaction",
            ],
        )
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
