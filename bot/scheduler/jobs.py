import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.engine import async_session
from bot.database.repository import GroupRepository
from bot.services.cleanup import CleanupService

logger = logging.getLogger(__name__)


async def run_autoclean(bot: Bot) -> None:
    async with async_session() as session:
        groups = await GroupRepository(session).get_autoclean_groups()
        for group in groups:
            period = GroupRepository.autoclean_period(group)
            await _clean_group(session, bot, group.group_id, period)


async def _clean_group(session: AsyncSession, bot: Bot, group_id: int, period) -> None:
    from bot.utils.duration import format_duration

    service = CleanupService(session, bot)
    result = await service.execute(group_id, period)
    if not result.removed:
        return
    label = format_duration(period)
    text = (
        f"🤖 <b>Автоочистка</b> (>{label})\n"
        f"Удалено: <b>{len(result.removed)}</b> участников"
    )
    try:
        await bot.send_message(group_id, text)
    except Exception as exc:
        logger.warning("Autoclean report failed for %s: %s", group_id, exc)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_autoclean, "cron", hour=3, minute=0, args=[bot], id="autoclean")
    return scheduler
