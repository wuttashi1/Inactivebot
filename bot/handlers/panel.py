import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import delete

from bot.callbacks import (
    AdminCb,
    AutoCleanCb,
    CleanCb,
    GroupCb,
    MembersCb,
    MenuCb,
    OwnerCb,
    ReportCb,
    RollcallCb,
    WarnCb,
    WhitelistCb,
)
from bot.database.engine import async_session
from bot.database.models import Admin, Group, User
from bot.database.repository import AdminRepository, GroupRepository, UserRepository
from bot.keyboards.menus import keyboards
from bot.middleware.admin import require_group_admin, require_group_owner
from bot.services.cleanup import CleanupService
from bot.services.reports import ReportService, format_inactive_list, format_stats, format_user_line
from bot.services.warnings import WarningService
from bot.services.binding import start_bind
from bot.states import PanelStates

logger = logging.getLogger(__name__)
router = Router()

USER_ID_PATTERN = re.compile(r"^\d{5,}$")


async def _deny(callback: CallbackQuery) -> None:
    await callback.answer("⛔ Нет доступа", show_alert=True)


async def _edit_or_answer(callback: CallbackQuery, text: str, markup=None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)


@router.callback_query(GroupCb.filter(F.action == "bind"))
async def bind_group_start(callback: CallbackQuery, state: FSMContext) -> None:
    start_bind(callback.from_user.id)
    await state.set_state(PanelStates.waiting_bind)
    await _edit_or_answer(
        callback,
        "🔗 <b>Привязка группы</b>\n\n"
        "1. <b>Сначала</b> нажмите эту кнопку (уже сделано ✅)\n"
        "2. Добавьте бота в группу\n"
        "3. Назначьте бота администратором\n\n"
        "Если бот уже в группе — снимите с админа и назначьте снова,\n"
        "или удалите из группы и добавьте заново.",
        keyboards.setup(),
    )
    await callback.answer()


@router.callback_query(GroupCb.filter(F.action == "select"))
async def select_group(callback: CallbackQuery, callback_data: GroupCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        group = await GroupRepository(session).get(callback_data.group_id)
        is_owner = await AdminRepository(session).is_owner(callback_data.group_id, callback.from_user.id)
    if not group:
        await callback.answer("Группа не найдена", show_alert=True)
        return
    await _edit_or_answer(
        callback,
        f"📊 <b>Activity Manager Panel</b>\nГруппа: <b>{group.title}</b>",
        keyboards.main_menu(group.group_id, is_owner),
    )
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "main"))
async def menu_main(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        group = await GroupRepository(session).get(callback_data.group_id)
        is_owner = await AdminRepository(session).is_owner(callback_data.group_id, callback.from_user.id)
    await _edit_or_answer(
        callback,
        f"📊 <b>Activity Manager Panel</b>\nГруппа: <b>{group.title if group else callback_data.group_id}</b>",
        keyboards.main_menu(callback_data.group_id, is_owner),
    )
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "stats"))
async def menu_stats(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        stats = await UserRepository(session).get_stats(callback_data.group_id)
    await _edit_or_answer(
        callback,
        format_stats(stats),
        keyboards.stats(callback_data.group_id),
    )
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "members"))
async def menu_members(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await _edit_or_answer(
        callback,
        "👥 <b>Участники</b>\n\nВыберите действие:",
        keyboards.members_menu(callback_data.group_id),
    )
    await callback.answer()


@router.callback_query(MembersCb.filter())
async def members_actions(callback: CallbackQuery, callback_data: MembersCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        repo = UserRepository(session)
        if callback_data.action == "top_active":
            users = await repo.get_top_active(callback_data.group_id)
            text = "🔥 <b>Топ активных</b>\n\n" + (
                "\n".join(format_user_line(u, i) for i, u in enumerate(users, 1)) or "— нет данных —"
            )
        elif callback_data.action == "top_inactive":
            users = await repo.get_top_inactive(callback_data.group_id)
            text = "📉 <b>Топ неактивных</b>\n\n" + (
                "\n".join(format_user_line(u, i) for i, u in enumerate(users, 1)) or "— нет данных —"
            )
        elif callback_data.action in ("candidates", "inactive"):
            users = await repo.get_inactive(callback_data.group_id, callback_data.days)
            text = format_inactive_list(users, callback_data.days)
        else:
            await callback.answer()
            return
    await _edit_or_answer(callback, text, keyboards.members_menu(callback_data.group_id))
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "clean"))
async def menu_clean(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await _edit_or_answer(
        callback,
        "🧹 <b>Очистка неактива</b>\n\nВыберите период неактивности:",
        keyboards.clean_periods(callback_data.group_id),
    )
    await callback.answer()


@router.callback_query(CleanCb.filter(F.action == "period"))
async def clean_period(callback: CallbackQuery, callback_data: CleanCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        count = await UserRepository(session).count_inactive(callback_data.group_id, callback_data.days)
    await _edit_or_answer(
        callback,
        f"⚠️ Найдено: <b>{count}</b> неактивных (>{callback_data.days} дней)",
        keyboards.clean_confirm(callback_data.group_id, callback_data.days, count),
    )
    await callback.answer()


@router.callback_query(CleanCb.filter(F.action == "preview"))
async def clean_preview(callback: CallbackQuery, callback_data: CleanCb, bot: Bot) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        service = CleanupService(session, bot)
        users = await service.preview(callback_data.group_id, callback_data.days)
    await _edit_or_answer(
        callback,
        format_inactive_list(users, callback_data.days, "👁 Список на удаление"),
        keyboards.clean_confirm(callback_data.group_id, callback_data.days, len(users)),
    )
    await callback.answer()


@router.callback_query(CleanCb.filter(F.action == "confirm"))
async def clean_confirm(callback: CallbackQuery, callback_data: CleanCb, bot: Bot) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await callback.answer("⏳ Выполняется очистка...")
    async with async_session() as session:
        service = CleanupService(session, bot)
        result = await service.execute(callback_data.group_id, callback_data.days)

    lines = [
        f"🧹 <b>Очистка завершена</b> (>{callback_data.days} дней)\n",
        f"✅ Удалено: <b>{len(result.removed)}</b>",
        f"⏭ Пропущено: <b>{len(result.skipped)}</b>",
        f"❌ Ошибок: <b>{len(result.failed)}</b>",
    ]
    if result.removed:
        lines.append("\n<b>Удалённые:</b>")
        for i, u in enumerate(result.removed[:20], 1):
            lines.append(format_user_line(u, i))

    report = "\n".join(lines)
    await _edit_or_answer(callback, report, keyboards.back(callback_data.group_id))
    try:
        await bot.send_message(callback_data.group_id, report)
    except Exception as exc:
        logger.warning("Cannot post cleanup report to group: %s", exc)


@router.callback_query(CleanCb.filter(F.action == "cancel"))
async def clean_cancel(callback: CallbackQuery, callback_data: CleanCb) -> None:
    await menu_main(callback, MenuCb(action="main", group_id=callback_data.group_id))


@router.callback_query(MenuCb.filter(F.action == "settings"))
async def menu_settings(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await _edit_or_answer(
        callback,
        "⚙️ <b>Настройки</b>",
        keyboards.settings_menu(callback_data.group_id),
    )
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "autoclean"))
async def menu_autoclean(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        group = await GroupRepository(session).get(callback_data.group_id)
    status = "🟢 Включена" if group and group.autoclean_enabled else "🔴 Выключена"
    days = group.autoclean_days if group else 30
    await _edit_or_answer(
        callback,
        f"🔔 <b>Автоочистка</b>\n\nСтатус: {status}\nПериод: <b>{days}</b> дней",
        keyboards.autoclean(callback_data.group_id, group.autoclean_enabled if group else False, days),
    )
    await callback.answer()


@router.callback_query(AutoCleanCb.filter(F.action == "toggle"))
async def autoclean_toggle(callback: CallbackQuery, callback_data: AutoCleanCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    enabled = callback_data.enabled == 1
    async with async_session() as session:
        await GroupRepository(session).set_autoclean(callback_data.group_id, enabled)
        group = await GroupRepository(session).get(callback_data.group_id)
    await _edit_or_answer(
        callback,
        f"🔔 Автоочистка: {'🟢 включена' if enabled else '🔴 выключена'}",
        keyboards.autoclean(callback_data.group_id, group.autoclean_enabled, group.autoclean_days),
    )
    await callback.answer()


@router.callback_query(AutoCleanCb.filter(F.action == "period"))
async def autoclean_period(callback: CallbackQuery, callback_data: AutoCleanCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        repo = GroupRepository(session)
        group = await repo.get(callback_data.group_id)
        await repo.set_autoclean(callback_data.group_id, group.autoclean_enabled if group else False, callback_data.days)
        group = await repo.get(callback_data.group_id)
    await callback.answer(f"Период: {callback_data.days} дней")
    await _edit_or_answer(
        callback,
        f"🔔 <b>Автоочистка</b>\nПериод: <b>{group.autoclean_days}</b> дней",
        keyboards.autoclean(callback_data.group_id, group.autoclean_enabled, group.autoclean_days),
    )


@router.callback_query(MenuCb.filter(F.action == "admins"))
async def menu_admins(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    is_owner = await require_group_owner(callback_data.group_id, callback.from_user.id)
    await _edit_or_answer(
        callback,
        "🛡 <b>Администраторы бота</b>",
        keyboards.admins_menu(callback_data.group_id, is_owner),
    )
    await callback.answer()


@router.callback_query(AdminCb.filter(F.action == "list"))
async def admins_list(callback: CallbackQuery, callback_data: AdminCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        admins = await AdminRepository(session).list_admins(callback_data.group_id)
    lines = ["🛡 <b>Список администраторов</b>\n"]
    for a in admins:
        role = "👑 Owner" if a.role == "owner" else "🛡 Admin"
        lines.append(f"{role}: <code>{a.user_id}</code>")
    await _edit_or_answer(callback, "\n".join(lines), keyboards.admins_menu(callback_data.group_id, False))
    await callback.answer()


@router.callback_query(AdminCb.filter(F.action == "add"))
async def admins_add_start(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext) -> None:
    if not await require_group_owner(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await state.set_state(PanelStates.add_admin)
    await state.update_data(group_id=callback_data.group_id)
    await _edit_or_answer(
        callback,
        "➕ Отправьте @username или Telegram ID нового администратора:",
        keyboards.back(callback_data.group_id),
    )
    await callback.answer()


@router.callback_query(AdminCb.filter(F.action == "remove"))
async def admins_remove_start(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext) -> None:
    if not await require_group_owner(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await state.set_state(PanelStates.remove_admin)
    await state.update_data(group_id=callback_data.group_id)
    await _edit_or_answer(
        callback,
        "➖ Отправьте @username или Telegram ID для удаления:",
        keyboards.back(callback_data.group_id),
    )
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "whitelist"))
async def menu_whitelist(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await _edit_or_answer(callback, "📋 <b>Белый список</b>", keyboards.whitelist_menu(callback_data.group_id))
    await callback.answer()


@router.callback_query(WhitelistCb.filter(F.action == "list"))
async def whitelist_list(callback: CallbackQuery, callback_data: WhitelistCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        users = await UserRepository(session).list_whitelist(callback_data.group_id)
    text = "📋 <b>Белый список</b>\n\n" + (
        "\n".join(format_user_line(u, i) for i, u in enumerate(users, 1)) or "— пусто —"
    )
    await _edit_or_answer(callback, text, keyboards.whitelist_menu(callback_data.group_id))
    await callback.answer()


@router.callback_query(WhitelistCb.filter(F.action == "add"))
async def whitelist_add_start(callback: CallbackQuery, callback_data: WhitelistCb, state: FSMContext) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await state.set_state(PanelStates.whitelist_add)
    await state.update_data(group_id=callback_data.group_id)
    await _edit_or_answer(callback, "➕ Отправьте @username или ID:", keyboards.back(callback_data.group_id))
    await callback.answer()


@router.callback_query(WhitelistCb.filter(F.action == "remove"))
async def whitelist_remove_start(callback: CallbackQuery, callback_data: WhitelistCb, state: FSMContext) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await state.set_state(PanelStates.whitelist_remove)
    await state.update_data(group_id=callback_data.group_id)
    await _edit_or_answer(callback, "➖ Отправьте @username или ID:", keyboards.back(callback_data.group_id))
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "reports"))
async def menu_reports(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await _edit_or_answer(callback, "📄 <b>Отчёты</b>", keyboards.reports_menu(callback_data.group_id))
    await callback.answer()


@router.callback_query(ReportCb.filter())
async def reports_generate(callback: CallbackQuery, callback_data: ReportCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        service = ReportService(session)
        text = await service.weekly(callback_data.group_id) if callback_data.action == "weekly" else await service.monthly(callback_data.group_id)
    await _edit_or_answer(callback, text, keyboards.reports_menu(callback_data.group_id))
    await callback.answer()


@router.callback_query(MenuCb.filter(F.action == "warn"))
async def menu_warn(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await _edit_or_answer(
        callback,
        "⚠️ <b>Уведомление неактивных</b>\n\nВыберите период:",
        keyboards.warn_periods(callback_data.group_id),
    )
    await callback.answer()


@router.callback_query(WarnCb.filter(F.action == "period"))
async def warn_period(callback: CallbackQuery, callback_data: WarnCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        count = await UserRepository(session).count_inactive(callback_data.group_id, callback_data.days)
    await _edit_or_answer(
        callback,
        f"📩 Будет отправлено уведомление <b>{count}</b> пользователям (>{callback_data.days} дней)",
        keyboards.warn_confirm(callback_data.group_id, callback_data.days),
    )
    await callback.answer()


@router.callback_query(WarnCb.filter(F.action == "send"))
async def warn_send(callback: CallbackQuery, callback_data: WarnCb, bot: Bot) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await callback.answer("📩 Отправка...")
    async with async_session() as session:
        service = WarningService(session, bot)
        sent, failed = await service.warn_inactive(callback_data.group_id, callback_data.days)
    await _edit_or_answer(
        callback,
        f"✅ Отправлено: <b>{sent}</b>\n❌ Не доставлено: <b>{failed}</b>",
        keyboards.back(callback_data.group_id),
    )


@router.callback_query(MenuCb.filter(F.action == "rollcall"))
async def menu_rollcall(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await _edit_or_answer(
        callback,
        "📣 <b>Перекличка</b>\n\nПодтвердите активность в течение 7 дней.",
        keyboards.rollcall_confirm(callback_data.group_id),
    )
    await callback.answer()


@router.callback_query(RollcallCb.filter(F.action == "start"))
async def rollcall_start(callback: CallbackQuery, callback_data: RollcallCb, bot: Bot) -> None:
    if not await require_group_admin(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    try:
        await bot.send_message(
            callback_data.group_id,
            "📣 <b>Перекличка</b>\n\nПодтвердите активность в течение 7 дней.",
            reply_markup=keyboards.rollcall_user(callback_data.group_id),
        )
        await callback.answer("✅ Перекличка опубликована")
    except Exception:
        await callback.answer("❌ Не удалось отправить в группу", show_alert=True)


@router.callback_query(MenuCb.filter(F.action == "owner"))
async def menu_owner(callback: CallbackQuery, callback_data: MenuCb) -> None:
    if not await require_group_owner(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await _edit_or_answer(callback, "👑 <b>Панель владельца</b>", keyboards.owner_menu(callback_data.group_id))
    await callback.answer()


@router.callback_query(OwnerCb.filter(F.action == "groups"))
async def owner_groups(callback: CallbackQuery, callback_data: OwnerCb) -> None:
    if not await require_group_owner(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        groups = await GroupRepository(session).get_user_groups(callback.from_user.id)
    lines = ["🗂 <b>Ваши группы</b>\n"]
    for g in groups:
        mark = "⭐ " if g.is_primary else ""
        lines.append(f"{mark}<b>{g.title}</b> — <code>{g.group_id}</code>")
    await _edit_or_answer(callback, "\n".join(lines), keyboards.owner_menu(callback_data.group_id))
    await callback.answer()


@router.callback_query(OwnerCb.filter(F.action == "transfer"))
async def owner_transfer_start(callback: CallbackQuery, callback_data: OwnerCb, state: FSMContext) -> None:
    if not await require_group_owner(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    await state.set_state(PanelStates.transfer_owner)
    await state.update_data(group_id=callback_data.group_id)
    await _edit_or_answer(callback, "👤 Отправьте ID нового владельца:", keyboards.owner_menu(callback_data.group_id))
    await callback.answer()


@router.callback_query(OwnerCb.filter(F.action == "reset"))
async def owner_reset(callback: CallbackQuery, callback_data: OwnerCb) -> None:
    if not await require_group_owner(callback_data.group_id, callback.from_user.id):
        await _deny(callback)
        return
    async with async_session() as session:
        await session.execute(delete(User).where(User.group_id == callback_data.group_id))
        await session.execute(
            delete(Admin).where(Admin.group_id == callback_data.group_id, Admin.role != "owner")
        )
        await session.commit()
    await callback.answer("🧨 Данные группы сброшены", show_alert=True)
    await menu_main(callback, MenuCb(action="main", group_id=callback_data.group_id))


async def _resolve_user_id(session, group_id: int, text: str) -> int | None:
    text = text.strip()
    if text.startswith("@"):
        user = await UserRepository(session).find_by_username(group_id, text)
        return user.user_id if user else None
    if USER_ID_PATTERN.match(text):
        return int(text)
    return None


@router.message(PanelStates.add_admin)
async def admins_add_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    group_id = data["group_id"]
    if not await require_group_owner(group_id, message.from_user.id):
        await message.answer("⛔ Нет доступа")
        await state.clear()
        return
    async with async_session() as session:
        target_id = await _resolve_user_id(session, group_id, message.text or "")
        if not target_id:
            await message.answer("❌ Пользователь не найден. Убедитесь, что он есть в группе.")
            return
        await AdminRepository(session).add_admin(group_id, target_id)
    await state.clear()
    await message.answer(
        f"✅ Администратор <code>{target_id}</code> добавлен",
        reply_markup=keyboards.main_menu(group_id, True),
    )


@router.message(PanelStates.remove_admin)
async def admins_remove_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    group_id = data["group_id"]
    if not await require_group_owner(group_id, message.from_user.id):
        await message.answer("⛔ Нет доступа")
        await state.clear()
        return
    async with async_session() as session:
        target_id = await _resolve_user_id(session, group_id, message.text or "")
        if not target_id:
            await message.answer("❌ Пользователь не найден.")
            return
        ok = await AdminRepository(session).remove_admin(group_id, target_id)
    await state.clear()
    await message.answer(
        "✅ Удалён" if ok else "❌ Не удалось удалить (возможно, это владелец)",
        reply_markup=keyboards.main_menu(group_id, True),
    )


@router.message(PanelStates.whitelist_add)
async def whitelist_add_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    group_id = data["group_id"]
    async with async_session() as session:
        target_id = await _resolve_user_id(session, group_id, message.text or "")
        if not target_id:
            await message.answer("❌ Пользователь не найден в группе.")
            return
        await UserRepository(session).set_whitelist(group_id, target_id, True)
    await state.clear()
    await message.answer("✅ Добавлен в белый список", reply_markup=keyboards.whitelist_menu(group_id))


@router.message(PanelStates.whitelist_remove)
async def whitelist_remove_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    group_id = data["group_id"]
    async with async_session() as session:
        target_id = await _resolve_user_id(session, group_id, message.text or "")
        if not target_id:
            await message.answer("❌ Пользователь не найден.")
            return
        await UserRepository(session).set_whitelist(group_id, target_id, False)
    await state.clear()
    await message.answer("✅ Удалён из белого списка", reply_markup=keyboards.whitelist_menu(group_id))


@router.message(PanelStates.transfer_owner)
async def transfer_owner_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    group_id = data["group_id"]
    if not await require_group_owner(group_id, message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not USER_ID_PATTERN.match(text):
        await message.answer("❌ Укажите числовой Telegram ID")
        return
    new_owner = int(text)
    old_owner = message.from_user.id
    async with async_session() as session:
        await GroupRepository(session).transfer_owner(group_id, old_owner, new_owner)
    await state.clear()
    await message.answer(
        f"✅ Владелец передан пользователю <code>{new_owner}</code>",
        reply_markup=keyboards.main_menu(group_id, False),
    )
