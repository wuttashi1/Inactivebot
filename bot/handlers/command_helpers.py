import re

from aiogram.types import Message

from bot.database.engine import async_session
from bot.database.repository import GroupRepository, UserRepository
from bot.middleware.admin import require_group_admin, require_group_owner

USER_REF_RE = re.compile(r"^@?\w+$|^\d{5,}$")


async def resolve_group_id(message: Message) -> int | None:
    if message.chat.type in ("group", "supergroup"):
        return message.chat.id

    async with async_session() as session:
        groups = await GroupRepository(session).get_user_groups(message.from_user.id)
    if not groups:
        return None
    for g in groups:
        if g.is_primary:
            return g.group_id
    return groups[0].group_id


async def ensure_admin(message: Message) -> int | None:
    group_id = await resolve_group_id(message)
    if not group_id:
        await message.answer("⛔ Группа не привязана. Используйте /bind")
        return None
    if not await require_group_admin(group_id, message.from_user.id):
        await message.answer("⛔ Нет прав администратора для этой группы")
        return None
    return group_id


async def ensure_owner(message: Message) -> int | None:
    group_id = await resolve_group_id(message)
    if not group_id:
        await message.answer("⛔ Группа не привязана. Используйте /bind")
        return None
    if not await require_group_owner(group_id, message.from_user.id):
        await message.answer("⛔ Только владелец может выполнить эту команду")
        return None
    return group_id


async def resolve_target_user(group_id: int, ref: str) -> int | None:
    ref = ref.strip()
    if ref.isdigit():
        return int(ref)
    if ref.startswith("@"):
        async with async_session() as session:
            user = await UserRepository(session).find_by_username(group_id, ref)
        return user.user_id if user else None
    return None


def command_args(message: Message, command: object) -> list[str]:
    if getattr(command, "args", None):
        return command.args.split()
    text = message.text or ""
    parts = text.split(maxsplit=1)
    return parts[1].split() if len(parts) > 1 else []
