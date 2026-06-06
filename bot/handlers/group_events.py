import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberUpdated, Message, MessageReactionUpdated

from bot.config import settings
from bot.database.engine import async_session
from bot.database.repository import GroupRepository, UserRepository
from bot.keyboards.menus import keyboards
from bot.states import PanelStates

logger = logging.getLogger(__name__)
router = Router()


@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def bot_added_to_group(event: ChatMemberUpdated, bot: Bot, state: FSMContext) -> None:
    chat = event.chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    adder_id = event.from_user.id
    current_state = await state.get_state()
    is_binding = current_state == PanelStates.waiting_bind

    if not is_binding and adder_id != settings.owner_id:
        return

    me = await bot.get_me()
    try:
        bot_member = await bot.get_chat_member(chat.id, me.id)
    except Exception:
        return

    if bot_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
        try:
            await bot.send_message(
                adder_id,
                "⚠️ Назначьте бота администратором группы для полного функционала.",
            )
        except Exception:
            pass
        return

    async with async_session() as session:
        group = await GroupRepository(session).bind_group(chat.id, chat.title or str(chat.id), adder_id)

    await state.clear()
    is_owner = adder_id == group.owner_id or adder_id == settings.owner_id
    try:
        await bot.send_message(
            adder_id,
            f"✅ Группа <b>{group.title}</b> привязана!\n\nОткройте панель управления:",
            reply_markup=keyboards.main_menu(group.group_id, is_owner),
        )
    except Exception as exc:
        logger.warning("Cannot notify binder: %s", exc)


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def track_message(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    async with async_session() as session:
        group_repo = GroupRepository(session)
        group = await group_repo.get(message.chat.id)
        if not group:
            return
        await UserRepository(session).record_message(
            message.chat.id,
            message.from_user.id,
            message.from_user.username,
            message.from_user.full_name,
        )


@router.message_reaction()
async def track_reaction(event: MessageReactionUpdated) -> None:
    if not event.user or event.user.is_bot:
        return
    chat_id = event.chat.id
    async with async_session() as session:
        group = await GroupRepository(session).get(chat_id)
        if not group:
            return
        await UserRepository(session).record_reaction(
            chat_id,
            event.user.id,
            event.user.username,
            event.user.full_name,
        )


@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def member_joined(event: ChatMemberUpdated) -> None:
    if not event.new_chat_member.user or event.new_chat_member.user.is_bot:
        return
    chat_id = event.chat.id
    user = event.new_chat_member.user
    async with async_session() as session:
        group = await GroupRepository(session).get(chat_id)
        if not group:
            return
        await UserRepository(session).upsert_member(
            chat_id,
            user.id,
            user.username,
            user.full_name,
        )
