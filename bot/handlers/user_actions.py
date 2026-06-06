from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.callbacks import ActiveCb, RollcallCb
from bot.database.engine import async_session
from bot.database.repository import UserRepository

router = Router()


@router.callback_query(ActiveCb.filter())
async def confirm_active(callback: CallbackQuery, callback_data: ActiveCb) -> None:
    async with async_session() as session:
        await UserRepository(session).touch_activity(callback_data.group_id, callback.from_user.id)
    await callback.answer("✅ Активность обновлена!", show_alert=True)


@router.callback_query(RollcallCb.filter(F.action == "confirm"))
async def rollcall_confirm(callback: CallbackQuery, callback_data: RollcallCb) -> None:
    async with async_session() as session:
        await UserRepository(session).touch_activity(callback_data.group_id, callback.from_user.id)
    await callback.answer("✅ Вы подтвердили активность!")
