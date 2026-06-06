import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from bot.database.engine import async_session
from bot.database.repository import UserRepository
from bot.services.sync import SyncService

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.RESTRICTED,
})

LEFT_STATUSES = frozenset({
    ChatMemberStatus.LEFT,
    ChatMemberStatus.KICKED,
})


@dataclass
class MemberParseResult:
    telegram_count: int | None = None
    pending_updates: int = 0
    messages_replayed: int = 0
    joins_replayed: int = 0
    admins_synced: int = 0
    candidates_checked: int = 0
    added: int = 0
    updated: int = 0
    reactivated: int = 0
    marked_left: int = 0
    errors: int = 0
    db_active_after: int = 0


class MemberParseService:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def parse_group(self, group_id: int) -> MemberParseResult:
        result = MemberParseResult()

        pending, counters = await SyncService(self.bot).drain_pending_updates()
        result.pending_updates = pending
        result.messages_replayed = counters["messages"]
        result.joins_replayed = counters["joins"]

        try:
            result.telegram_count = await self.bot.get_chat_member_count(group_id)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            logger.warning("Cannot get member count for %s: %s", group_id, exc)
            result.errors += 1

        try:
            administrators = await self.bot.get_chat_administrators(group_id)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            logger.warning("Cannot get administrators for %s: %s", group_id, exc)
            result.errors += 1
            return result

        candidate_ids: set[int] = set()
        admin_profiles: dict[int, tuple[str | None, str]] = {}

        for admin in administrators:
            if admin.user.is_bot:
                continue
            candidate_ids.add(admin.user.id)
            admin_profiles[admin.user.id] = (admin.user.username, admin.user.full_name)
            result.admins_synced += 1

        async with async_session() as session:
            users_repo = UserRepository(session)
            known_ids = await users_repo.list_known_user_ids(group_id)
            existing_active = {
                u.user_id: u.is_active
                for u in await users_repo.list_all_users(group_id)
            }

        candidate_ids.update(known_ids)

        for user_id in sorted(candidate_ids):
            result.candidates_checked += 1
            username, first_name = admin_profiles.get(user_id, (None, ""))

            try:
                member = await self._get_member(group_id, user_id)
            except (TelegramBadRequest, TelegramForbiddenError):
                result.errors += 1
                continue

            if member.user and not member.user.is_bot:
                username = member.user.username
                first_name = member.user.full_name

            if member.status in LEFT_STATUSES:
                if existing_active.get(user_id):
                    async with async_session() as session:
                        await UserRepository(session).mark_removed(group_id, user_id)
                    result.marked_left += 1
                continue

            if member.status not in ACTIVE_STATUSES:
                continue

            was_known = user_id in existing_active
            was_active = existing_active.get(user_id, False)

            async with async_session() as session:
                _, created = await UserRepository(session).upsert_parsed_member(
                    group_id,
                    user_id,
                    username,
                    first_name or "",
                )

            if created:
                result.added += 1
            elif was_known and not was_active:
                result.reactivated += 1
            elif was_known:
                result.updated += 1
            else:
                result.added += 1

        async with async_session() as session:
            result.db_active_after = await UserRepository(session).count_active_users(group_id)

        return result

    async def _get_member(self, group_id: int, user_id: int):
        while True:
            try:
                member = await self.bot.get_chat_member(group_id, user_id)
                await asyncio.sleep(0.04)
                return member
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 0.5)
            except (TelegramBadRequest, TelegramForbiddenError):
                raise


def format_parse_result(result: MemberParseResult) -> str:
    lines = [
        "✅ <b>Синхронизация участников завершена</b>\n",
        f"📥 Обработано обновлений: <b>{result.pending_updates}</b> "
        f"(сообщений: {result.messages_replayed}, вступлений: {result.joins_replayed})",
        f"👑 Администраторов в группе: <b>{result.admins_synced}</b>",
        f"🔍 Проверено ID: <b>{result.candidates_checked}</b>",
        f"➕ Добавлено в базу: <b>{result.added}</b>",
        f"🔄 Обновлено профилей: <b>{result.updated}</b>",
        f"♻️ Восстановлено (были неактивны): <b>{result.reactivated}</b>",
        f"🚪 Отмечено как вышедшие: <b>{result.marked_left}</b>",
        f"❌ Ошибок API: <b>{result.errors}</b>",
        f"📊 В базе активных: <b>{result.db_active_after}</b>",
    ]

    if result.telegram_count is not None:
        lines.append(f"📱 Участников в Telegram: <b>{result.telegram_count}</b>")
        gap = result.telegram_count - result.db_active_after
        if gap > 0:
            lines.append(
                f"\n⚠️ В Telegram на <b>{gap}</b> участников больше, чем в базе.\n"
                "<i>Bot API не отдаёт полный список участников. "
                "В базу попадают администраторы, известные пользователи и те, "
                "кто писал/реагировал после добавления бота. "
                "Остальные появятся после сообщения или переклички.</i>"
            )

    return "\n".join(lines)
