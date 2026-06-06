import logging
from dataclasses import dataclass
from datetime import timedelta

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.database.repository import UserRepository

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    removed: list[User]
    skipped: list[tuple[User, str]]
    failed: list[tuple[User, str]]


class CleanupService:
    def __init__(self, session: AsyncSession, bot: Bot) -> None:
        self.session = session
        self.bot = bot
        self.users = UserRepository(session)

    async def _should_skip(self, group_id: int, user: User) -> str | None:
        if user.whitelisted:
            return "whitelist"
        try:
            member = await self.bot.get_chat_member(group_id, user.user_id)
        except (TelegramBadRequest, TelegramForbiddenError):
            return "unreachable"

        if member.status == ChatMemberStatus.CREATOR:
            return "owner"
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            return "admin"
        return None

    async def preview(self, group_id: int, period: timedelta | int) -> list[User]:
        return await self.users.get_inactive(group_id, period, limit=100)

    async def preview_zero(self, group_id: int, membership_period: timedelta | int) -> list[User]:
        return await self.users.get_zero_activity(group_id, membership_period, limit=100)

    async def execute(self, group_id: int, period: timedelta | int) -> CleanupResult:
        candidates = await self.users.get_inactive(group_id, period, limit=500)
        return await self._remove_users(group_id, candidates, reason="inactive")

    async def execute_zero(self, group_id: int, membership_period: timedelta | int) -> CleanupResult:
        candidates = await self.users.get_zero_activity(group_id, membership_period, limit=500)
        return await self._remove_users(group_id, candidates, reason="zero_activity")

    async def _remove_users(
        self,
        group_id: int,
        candidates: list[User],
        *,
        reason: str,
    ) -> CleanupResult:
        removed: list[User] = []
        skipped: list[tuple[User, str]] = []
        failed: list[tuple[User, str]] = []

        for user in candidates:
            skip_reason = await self._should_skip(group_id, user)
            if skip_reason:
                skipped.append((user, skip_reason))
                continue
            try:
                await self.bot.ban_chat_member(group_id, user.user_id)
                await self.bot.unban_chat_member(group_id, user.user_id)
                await self.users.save_cleanup_backup(group_id, user, reason=reason)
                await self.users.mark_removed(group_id, user.user_id)
                removed.append(user)
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                logger.warning("Failed to remove user %s: %s", user.user_id, exc)
                failed.append((user, str(exc)))

        return CleanupResult(removed=removed, skipped=skipped, failed=failed)
