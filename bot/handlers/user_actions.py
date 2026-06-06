from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.callbacks import ActiveCb, RollcallCb
from bot.database.engine import async_session
from bot.database.repository import UserRepository

router = Router()


@router.callback_query(ActiveCb.filter())
async def confirm_active(callback: CallbackQuery, callback_data: ActiveCb) -> None:
    user = callback.from_user
    async with async_session() as session:
        repo = UserRepository(session)
        existing = await repo.get_user(callback_data.group_id, user.id)
        if existing:
            await repo.touch_activity(callback_data.group_id, user.id)
        else:
            await repo.upsert_member(
                callback_data.group_id,
                user.id,
                user.username,
                user.full_name,
            )
    await callback.answer("✅ Активность обновлена!", show_alert=True)


@router.callback_query(RollcallCb.filter(F.action == "confirm"))
async def rollcall_confirm(callback: CallbackQuery, callback_data: RollcallCb) -> None:
    user = callback.from_user
    async with async_session() as session:
        repo = UserRepository(session)
        existing = await repo.get_user(callback_data.group_id, user.id)
        if existing:
            await repo.touch_activity(callback_data.group_id, user.id)
        else:
            await repo.upsert_member(
                callback_data.group_id,
                user.id,
                user.username,
                user.full_name,
            )
    await callback.answer("✅ Вы подтвердили активность!")
