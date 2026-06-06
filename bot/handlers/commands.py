import logging

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BotCommand, Message

from bot.database.engine import async_session
from bot.database.repository import AdminRepository, GroupRepository, UserRepository
from bot.handlers.command_helpers import (
    command_args,
    ensure_admin,
    ensure_owner,
    resolve_group_id,
    resolve_target_user,
)
from bot.keyboards.menus import keyboards
from bot.services.binding import start_bind
from bot.services.cleanup import CleanupService
from bot.services.reports import ReportService, format_inactive_list, format_stats, format_user_line
from bot.services.warnings import WarningService
from bot.utils.duration import DurationParseError, format_duration, parse_duration

logger = logging.getLogger(__name__)
router = Router()

HELP_TEXT = (
    "📖 <b>Команды Activity Manager</b>\n\n"
    "<b>Группа</b>\n"
    "/bind — привязать группу\n"
    "/stats — статистика\n\n"
    "<b>Активность</b> (свой период: 4sec, 5h, 30d, 2w)\n"
    "/inactive 30d — список неактивных\n"
    "/warninactive 5h — уведомить неактивных\n"
    "/cleaninactive 14d preview — просмотр\n"
    "/cleaninactive 14d confirm — удалить\n"
    "/rollcall — перекличка\n\n"
    "<b>Настройки</b>\n"
    "/autoclean on|off — вкл/выкл автоочистку\n"
    "/autoclean 30d — период автоочистки\n\n"
    "<b>Админы</b> (только owner)\n"
    "/addadmin @user — добавить\n"
    "/removeadmin @user — удалить\n"
    "/admins — список\n\n"
    "<b>Белый список</b>\n"
    "/whitelist — список\n"
    "/whitelist @user — добавить\n"
    "/unwhitelist @user — удалить\n\n"
    "<b>Отчёты</b>\n"
    "/weeklyreport — за неделю\n"
    "/monthlyreport — за месяц\n\n"
    "Единицы: <code>sec/s</code>, <code>min/m</code>, <code>h</code>, <code>d</code>, <code>w</code>\n"
    "Число без единицы = дни (например <code>/inactive 7</code>)"
)

BOT_COMMANDS = [
    BotCommand(command="start", description="Открыть панель"),
    BotCommand(command="help", description="Список команд"),
    BotCommand(command="bind", description="Привязать группу"),
    BotCommand(command="stats", description="Статистика"),
    BotCommand(command="inactive", description="Неактивные (период)"),
    BotCommand(command="warninactive", description="Уведомить неактивных"),
    BotCommand(command="cleaninactive", description="Очистка неактивных"),
    BotCommand(command="rollcall", description="Перекличка"),
    BotCommand(command="autoclean", description="Автоочистка"),
    BotCommand(command="admins", description="Список админов"),
    BotCommand(command="whitelist", description="Белый список"),
    BotCommand(command="weeklyreport", description="Отчёт за неделю"),
    BotCommand(command="monthlyreport", description="Отчёт за месяц"),
]


def _parse_period_arg(args: list[str], default: str = "30d"):
    token = args[0] if args else default
    return parse_duration(token)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("bind"))
async def cmd_bind(message: Message) -> None:
    if message.chat.type != "private":
        await message.answer("Команду /bind используйте в личных сообщениях с ботом.")
        return
    start_bind(message.from_user.id)
    await message.answer(
        "🔗 <b>Привязка группы</b>\n\n"
        "1. Добавьте бота в группу\n"
        "2. Назначьте администратором\n\n"
        "Если бот уже в группе — снимите и назначьте админом снова.",
        reply_markup=keyboards.setup(),
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    async with async_session() as session:
        stats = await UserRepository(session).get_stats(group_id)
    await message.answer(format_stats(stats))


@router.message(Command("inactive"))
async def cmd_inactive(message: Message, command: CommandObject) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    args = command_args(message, command)
    try:
        period = _parse_period_arg(args, "30d")
    except DurationParseError as exc:
        await message.answer(f"❌ {exc}")
        return
    async with async_session() as session:
        users = await UserRepository(session).get_inactive(group_id, period)
    label = format_duration(period)
    await message.answer(format_inactive_list(users, period, f"👥 Неактивные более {label}"))


@router.message(Command("warninactive"))
async def cmd_warninactive(message: Message, command: CommandObject, bot: Bot) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    args = command_args(message, command)
    try:
        period = _parse_period_arg(args, "30d")
    except DurationParseError as exc:
        await message.answer(f"❌ {exc}")
        return
    async with async_session() as session:
        service = WarningService(session, bot)
        sent, failed = await service.warn_inactive(group_id, period)
    label = format_duration(period)
    await message.answer(
        f"📩 Уведомления ({label})\n✅ Отправлено: <b>{sent}</b>\n❌ Не доставлено: <b>{failed}</b>"
    )


@router.message(Command("cleaninactive"))
async def cmd_cleaninactive(message: Message, command: CommandObject, bot: Bot) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    args = command_args(message, command)
    if not args:
        await message.answer(
            "Использование:\n"
            "<code>/cleaninactive 30d preview</code>\n"
            "<code>/cleaninactive 5h confirm</code>"
        )
        return

    mode = args[-1].lower() if len(args) > 1 else "preview"
    period_args = args[:-1] if len(args) > 1 else args
    if mode not in ("preview", "confirm"):
        period_args = args
        mode = "preview"

    try:
        period = _parse_period_arg(period_args, "30d")
    except DurationParseError as exc:
        await message.answer(f"❌ {exc}")
        return

    label = format_duration(period)
    async with async_session() as session:
        service = CleanupService(session, bot)
        if mode == "preview":
            users = await service.preview(group_id, period)
            await message.answer(
                format_inactive_list(users, period, f"👁 На удаление (>{label})")
            )
            return

        result = await service.execute(group_id, period)
    lines = [
        f"🧹 <b>Очистка завершена</b> (>{label})\n",
        f"✅ Удалено: <b>{len(result.removed)}</b>",
        f"⏭ Пропущено: <b>{len(result.skipped)}</b>",
        f"❌ Ошибок: <b>{len(result.failed)}</b>",
    ]
    if result.removed:
        lines.append("\n<b>Удалённые:</b>")
        for i, u in enumerate(result.removed[:15], 1):
            lines.append(format_user_line(u, i))
    report = "\n".join(lines)
    await message.answer(report)
    if message.chat.type in ("group", "supergroup"):
        return
    try:
        await bot.send_message(group_id, report)
    except Exception as exc:
        logger.warning("Cleanup report to group failed: %s", exc)


@router.message(Command("rollcall"))
async def cmd_rollcall(message: Message, bot: Bot) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    try:
        await bot.send_message(
            group_id,
            "📣 <b>Перекличка</b>\n\nПодтвердите активность в течение 7 дней.",
            reply_markup=keyboards.rollcall_user(group_id),
        )
        await message.answer("✅ Перекличка опубликована в группе")
    except Exception:
        await message.answer("❌ Не удалось отправить в группу. Проверьте права бота.")


@router.message(Command("autoclean"))
async def cmd_autoclean(message: Message, command: CommandObject) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    args = command_args(message, command)
    if not args:
        async with async_session() as session:
            group = await GroupRepository(session).get(group_id)
        if not group:
            return
        period = GroupRepository.autoclean_period(group)
        status = "🟢 вкл" if group.autoclean_enabled else "🔴 выкл"
        await message.answer(
            f"🔔 Автоочистка: {status}\nПериод: <b>{format_duration(period)}</b>\n\n"
            "Примеры:\n<code>/autoclean on</code>\n<code>/autoclean off</code>\n<code>/autoclean 5h</code>"
        )
        return

    arg = args[0].lower()
    async with async_session() as session:
        repo = GroupRepository(session)
        group = await repo.get(group_id)
        if arg == "on":
            await repo.set_autoclean(group_id, True)
            await message.answer("🟢 Автоочистка включена")
            return
        if arg == "off":
            await repo.set_autoclean(group_id, False)
            await message.answer("🔴 Автоочистка выключена")
            return
        try:
            period = parse_duration(arg)
        except DurationParseError as exc:
            await message.answer(f"❌ {exc}")
            return
        await repo.set_autoclean(group_id, group.autoclean_enabled if group else True, period)
    await message.answer(f"⏱ Период автоочистки: <b>{format_duration(period)}</b>")


@router.message(Command("admins"))
async def cmd_admins(message: Message) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    async with async_session() as session:
        admins = await AdminRepository(session).list_admins(group_id)
    lines = ["🛡 <b>Администраторы бота</b>\n"]
    for a in admins:
        role = "👑 Owner" if a.role == "owner" else "🛡 Admin"
        lines.append(f"{role}: <code>{a.user_id}</code>")
    await message.answer("\n".join(lines))


@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message, command: CommandObject) -> None:
    group_id = await ensure_owner(message)
    if not group_id:
        return
    args = command_args(message, command)
    if not args:
        await message.answer("Использование: <code>/addadmin @username</code> или <code>/addadmin 123456789</code>")
        return
    async with async_session() as session:
        target_id = await resolve_target_user(group_id, args[0])
        if not target_id:
            await message.answer("❌ Пользователь не найден в группе.")
            return
        await AdminRepository(session).add_admin(group_id, target_id)
    await message.answer(f"✅ Администратор <code>{target_id}</code> добавлен")


@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message, command: CommandObject) -> None:
    group_id = await ensure_owner(message)
    if not group_id:
        return
    args = command_args(message, command)
    if not args:
        await message.answer("Использование: <code>/removeadmin @username</code>")
        return
    async with async_session() as session:
        target_id = await resolve_target_user(group_id, args[0])
        if not target_id:
            await message.answer("❌ Пользователь не найден.")
            return
        ok = await AdminRepository(session).remove_admin(group_id, target_id)
    await message.answer("✅ Удалён" if ok else "❌ Не удалось (возможно, это владелец)")


@router.message(Command("whitelist"))
async def cmd_whitelist(message: Message, command: CommandObject) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    args = command_args(message, command)
    if not args:
        async with async_session() as session:
            users = await UserRepository(session).list_whitelist(group_id)
        text = "📋 <b>Белый список</b>\n\n" + (
            "\n".join(format_user_line(u, i) for i, u in enumerate(users, 1)) or "— пусто —"
        )
        await message.answer(text)
        return
    async with async_session() as session:
        target_id = await resolve_target_user(group_id, args[0])
        if not target_id:
            await message.answer("❌ Пользователь не найден в группе.")
            return
        await UserRepository(session).set_whitelist(group_id, target_id, True)
    await message.answer("✅ Добавлен в белый список")


@router.message(Command("unwhitelist"))
async def cmd_unwhitelist(message: Message, command: CommandObject) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    args = command_args(message, command)
    if not args:
        await message.answer("Использование: <code>/unwhitelist @username</code>")
        return
    async with async_session() as session:
        target_id = await resolve_target_user(group_id, args[0])
        if not target_id:
            await message.answer("❌ Пользователь не найден.")
            return
        await UserRepository(session).set_whitelist(group_id, target_id, False)
    await message.answer("✅ Удалён из белого списка")


@router.message(Command("weeklyreport"))
async def cmd_weeklyreport(message: Message) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    async with async_session() as session:
        text = await ReportService(session).weekly(group_id)
    await message.answer(text)


@router.message(Command("monthlyreport"))
async def cmd_monthlyreport(message: Message) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    async with async_session() as session:
        text = await ReportService(session).monthly(group_id)
    await message.answer(text)


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(BOT_COMMANDS)
