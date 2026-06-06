import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repository import UserRepository
from bot.keyboards.menus import keyboards
from bot.utils.duration import format_duration

logger = logging.getLogger(__name__)


class WarningService:
    def __init__(self, session: AsyncSession, bot: Bot) -> None:
        self.session = session
        self.bot = bot
        self.users = UserRepository(session)

    async def warn_inactive(self, group_id: int, period: timedelta | int) -> tuple[int, int]:
        td = timedelta(days=period) if isinstance(period, int) else period
        inactive = await self.users.get_inactive(group_id, td, limit=200)
        sent = 0
        failed = 0
        label = format_duration(td)
        text = (
            f"⚠️ Вы не проявляли активность более <b>{label}</b>.\n"
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
