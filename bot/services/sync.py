import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Update

from bot.config import settings
from bot.database.engine import async_session
from bot.database.repository import BotStateRepository, GroupRepository, UserRepository, utcnow

logger = logging.getLogger(__name__)

SYNC_ALLOWED_UPDATES = [
    "message",
    "message_reaction",
    "chat_member",
]

LEFT_STATUSES = frozenset({
    ChatMemberStatus.LEFT,
    ChatMemberStatus.KICKED,
})


@dataclass
class GroupSyncResult:
    group_id: int
    title: str
    members_checked: int = 0
    members_left: int = 0
    admins_registered: int = 0
    errors: int = 0


@dataclass
class SyncResult:
    downtime: timedelta | None
    pending_updates: int = 0
    messages_applied: int = 0
    reactions_applied: int = 0
    joins_applied: int = 0
    groups: list[GroupSyncResult] = field(default_factory=list)


class SyncService:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def run_startup_sync(self) -> SyncResult:
        async with async_session() as session:
            state_repo = BotStateRepository(session)
            state = await state_repo.record_startup()
            downtime = None
            if state.last_shutdown_at and state.last_startup_at:
                downtime = state.last_startup_at - state.last_shutdown_at

        result = SyncResult(downtime=downtime)
        result.pending_updates, counters = await self._drain_pending_updates()
        result.messages_applied = counters["messages"]
        result.reactions_applied = counters["reactions"]
        result.joins_applied = counters["joins"]

        async with async_session() as session:
            groups = await GroupRepository(session).get_all_bound()
        for group in groups:
            group_result = await self._sync_group_membership(group.group_id, group.title or str(group.group_id))
            result.groups.append(group_result)

        logger.info(
            "Startup sync: downtime=%s updates=%s msgs=%s groups=%s",
            downtime,
            result.pending_updates,
            result.messages_applied,
            len(result.groups),
        )
        return result

    async def drain_pending_updates(self) -> tuple[int, dict[str, int]]:
        return await self._drain_pending_updates()

    async def _drain_pending_updates(self) -> tuple[int, dict[str, int]]:
        counters = {"messages": 0, "reactions": 0, "joins": 0}
        total = 0
        offset: int | None = None
        max_batches = 200

        async with async_session() as session:
            saved = await BotStateRepository(session).get_last_update_id()
            if saved is not None:
                offset = saved + 1

        for _ in range(max_batches):
            try:
                updates = await self.bot.get_updates(
                    offset=offset,
                    limit=100,
                    timeout=0,
                    allowed_updates=SYNC_ALLOWED_UPDATES,
                )
            except Exception as exc:
                logger.warning("get_updates failed during sync: %s", exc)
                break

            if not updates:
                break

            for update in updates:
                applied = await self._apply_update(update)
                counters["messages"] += applied["messages"]
                counters["reactions"] += applied["reactions"]
                counters["joins"] += applied["joins"]
                total += 1
                offset = update.update_id + 1

            if offset is not None:
                async with async_session() as session:
                    await BotStateRepository(session).save_last_update_id(offset - 1)

            if len(updates) < 100:
                break

            await asyncio.sleep(0.05)

        return total, counters

    async def _apply_update(self, update: Update) -> dict[str, int]:
        applied = {"messages": 0, "reactions": 0, "joins": 0}

        if update.message and update.message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            msg = update.message
            if msg.from_user and not msg.from_user.is_bot:
                async with async_session() as session:
                    if await GroupRepository(session).get(msg.chat.id):
                        await UserRepository(session).record_message(
                            msg.chat.id,
                            msg.from_user.id,
                            msg.from_user.username,
                            msg.from_user.full_name,
                        )
                        applied["messages"] = 1

        if update.message_reaction and update.message_reaction.user:
            event = update.message_reaction
            if not event.user.is_bot and event.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                async with async_session() as session:
                    if await GroupRepository(session).get(event.chat.id):
                        await UserRepository(session).record_reaction(
                            event.chat.id,
                            event.user.id,
                            event.user.username,
                            event.user.full_name,
                        )
                        applied["reactions"] = 1

        if update.chat_member and update.chat_member.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            cm = update.chat_member
            new = cm.new_chat_member
            old = cm.old_chat_member
            if (
                new.user
                and not new.user.is_bot
                and new.status not in LEFT_STATUSES
                and old.status in LEFT_STATUSES
            ):
                async with async_session() as session:
                    if await GroupRepository(session).get(cm.chat.id):
                        await UserRepository(session).upsert_member(
                            cm.chat.id,
                            new.user.id,
                            new.user.username,
                            new.user.full_name,
                        )
                        applied["joins"] = 1

        return applied

    async def _sync_group_membership(self, group_id: int, title: str) -> GroupSyncResult:
        result = GroupSyncResult(group_id=group_id, title=title)

        try:
            admins = await self.bot.get_chat_administrators(group_id)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            logger.warning("Cannot get admins for %s: %s", group_id, exc)
            result.errors += 1
            return result

        async with async_session() as session:
            users_repo = UserRepository(session)
            for member in admins:
                if member.user.is_bot:
                    continue
                await users_repo.upsert_member(
                    group_id,
                    member.user.id,
                    member.user.username,
                    member.user.full_name,
                )
                result.admins_registered += 1

            known_users = await users_repo.list_active_users(group_id)

        for user in known_users:
            result.members_checked += 1
            try:
                member = await self.bot.get_chat_member(group_id, user.user_id)
            except (TelegramBadRequest, TelegramForbiddenError):
                result.errors += 1
                await asyncio.sleep(0.05)
                continue

            if member.status in LEFT_STATUSES:
                async with async_session() as session:
                    await UserRepository(session).mark_removed(group_id, user.user_id)
                result.members_left += 1

            await asyncio.sleep(0.04)

        return result

    async def notify_owner(self, result: SyncResult) -> None:
        if not settings.sync_notify_owner:
            return

        lines = ["🔄 <b>Синхронизация после запуска</b>\n"]
        if result.downtime:
            hours = int(result.downtime.total_seconds() // 3600)
            mins = int((result.downtime.total_seconds() % 3600) // 60)
            lines.append(f"⏱ Простой: <b>{hours} ч. {mins} мин.</b>")
        else:
            lines.append("⏱ Первый запуск или простой неизвестен")

        lines.append(f"📥 Обработано обновлений Telegram: <b>{result.pending_updates}</b>")
        lines.append(
            f"💬 Сообщений: <b>{result.messages_applied}</b> | "
            f"👍 Реакций: <b>{result.reactions_applied}</b> | "
            f"➕ Вступлений: <b>{result.joins_applied}</b>"
        )

        if result.groups:
            lines.append("\n<b>Группы:</b>")
            for g in result.groups:
                lines.append(
                    f"• {g.title}: проверено {g.members_checked}, "
                    f"вышли {g.members_left}, ошибок {g.errors}"
                )

        lines.append(
            "\n<i>Telegram хранит обновления до ~24 ч. "
            "Активность старше этого не восстановить.</i>"
        )

        try:
            await self.bot.send_message(settings.owner_id, "\n".join(lines))
        except Exception as exc:
            logger.warning("Cannot notify owner about sync: %s", exc)


async def record_shutdown() -> None:
    async with async_session() as session:
        await BotStateRepository(session).record_shutdown()
