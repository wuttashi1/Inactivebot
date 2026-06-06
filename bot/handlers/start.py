from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.config import settings
from bot.database.engine import async_session
from bot.database.repository import AdminRepository, GroupRepository
from bot.keyboards.menus import keyboards

router = Router()


async def show_panel(message: Message, user_id: int) -> None:
    async with async_session() as session:
        groups_repo = GroupRepository(session)
        admin_repo = AdminRepository(session)
        groups = await groups_repo.get_user_groups(user_id)

        if not groups and user_id == settings.owner_id:
            await message.answer(
                "📌 <b>Activity Manager Panel</b>\n\n"
                "Сначала нажмите кнопку ниже, затем добавьте меня в группу как администратора:",
                reply_markup=keyboards.setup(),
            )
            return

        if not groups:
            await message.answer(
                "⛔ У вас нет доступа к панели управления.\n"
                "Обратитесь к владельцу бота."
            )
            return

        if len(groups) == 1:
            g = groups[0]
            is_owner = await admin_repo.is_owner(g.group_id, user_id) or user_id == settings.owner_id
            await message.answer(
                f"📊 <b>Activity Manager Panel</b>\n"
                f"Группа: <b>{g.title}</b>\n\n"
                "Выберите действие:",
                reply_markup=keyboards.main_menu(g.group_id, is_owner),
            )
            return

        await message.answer(
            "📊 <b>Activity Manager Panel</b>\n\nВыберите группу:",
            reply_markup=keyboards.group_select(groups),
        )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await show_panel(message, message.from_user.id)


@router.message(F.chat.type == "private", F.text)
async def private_fallback(message: Message) -> None:
    if message.text and message.text.startswith("/"):
        return
    await show_panel(message, message.from_user.id)
