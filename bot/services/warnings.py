import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from bot.keyboards.menus import keyboards
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repository import UserRepository

logger = logging.getLogger(__name__)


class WarningService:
    def __init__(self, session: AsyncSession, bot: Bot) -> None:
        self.session = session
        self.bot = bot
        self.users = UserRepository(session)

    async def warn_inactive(self, group_id: int, days: int) -> tuple[int, int]:
        inactive = await self.users.get_inactive(group_id, days, limit=200)
        sent = 0
        failed = 0
        text = (
            f"⚠️ Вы не проявляли активность более <b>{days}</b> дней.\n"
            "Если хотите остаться в сообществе, нажмите кнопку ниже."
        )
        for user in inactive:
            try:
                await self.bot.send_message(
                    user.user_id,
                    text,
                    reply_markup=keyboards.i_am_active(group_id),
                )
                sent += 1
            except TelegramForbiddenError:
                failed += 1
                logger.info("Cannot DM user %s", user.user_id)
        return sent, failed
