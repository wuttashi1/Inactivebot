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
from bot.services.member_parse import MemberParseService, format_parse_result
from bot.services.reports import (
    ReportService,
    format_inactive_list,
    format_stats,
    format_user_line,
    format_zero_activity_list,
)
from bot.services.warnings import WarningService
from bot.utils.duration import DurationParseError, format_duration, parse_duration

logger = logging.getLogger(__name__)
router = Router()

HELP_TEXT = (
    "📖 <b>Команды Activity Manager</b>\n\n"
    "<b>Группа</b>\n"
    "/bind — привязать группу\n"
    "/unbind confirm — отвязать группу от бота\n"
    "/stats — статистика\n\n"
    "<b>Активность</b> (свой период: 4sec, 5h, 30d, 2w)\n"
    "/inactive 30d — список неактивных\n"
    "/warninactive 5h — уведомить неактивных\n"
    "/cleaninactive 14d preview — просмотр\n"
    "/cleaninactive 14d confirm — удалить\n"
    "/zero 30d — 0 сообщений и 0 реакций, в группе ≥30д\n"
    "/cleanzero 30d preview — просмотр кика\n"
    "/cleanzero 30d confirm — кикнуть таких\n"
    "/rollcall — перекличка\n\n"
    "<b>Настройки</b>\n"
    "/autoclean on|off — вкл/выкл автоочистку\n"
    "/autoclean 30d — свой период (5h, 4sec, 2w…)\n\n"
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
    "<b>Участники</b>\n"
    "/parsemembers — синхронизировать всех известных участников с базой\n\n"
    "Единицы: <code>sec/s</code>, <code>min/m</code>, <code>h</code>, <code>d</code>, <code>w</code>\n"
    "Число без единицы = дни (например <code>/inactive 7</code>)"
)

BOT_COMMANDS = [
    BotCommand(command="start", description="Открыть панель"),
    BotCommand(command="help", description="Список команд"),
    BotCommand(command="bind", description="Привязать группу"),
    BotCommand(command="unbind", description="Отвязать группу"),
    BotCommand(command="stats", description="Статистика"),
    BotCommand(command="inactive", description="Неактивные (период)"),
    BotCommand(command="warninactive", description="Уведомить неактивных"),
    BotCommand(command="cleaninactive", description="Очистка неактивных"),
    BotCommand(command="zero", description="Участники с 0 активностью"),
    BotCommand(command="cleanzero", description="Кик 0 активности"),
    BotCommand(command="rollcall", description="Перекличка"),
    BotCommand(command="autoclean", description="Автоочистка"),
    BotCommand(command="admins", description="Список админов"),
    BotCommand(command="whitelist", description="Белый список"),
    BotCommand(command="weeklyreport", description="Отчёт за неделю"),
    BotCommand(command="monthlyreport", description="Отчёт за месяц"),
    BotCommand(command="parsemembers", description="Синхронизация участников"),
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


@router.message(Command("unbind"))
async def cmd_unbind(message: Message, command: CommandObject) -> None:
    group_id = await ensure_owner(message)
    if not group_id:
        return

    args = command_args(message, command)
    if not args or args[0].lower() != "confirm":
        async with async_session() as session:
            group = await GroupRepository(session).get(group_id)
        title = group.title if group else str(group_id)
        await message.answer(
            f"🔓 <b>Отвязка группы</b>\n\n"
            f"Группа: <b>{title}</b>\n"
            f"ID: <code>{group_id}</code>\n\n"
            "Бот перестанет отслеживать активность. "
            "Все данные группы в базе будут удалены.\n"
            "Сам бот останется в Telegram-группе — удалите его вручную, если нужно.\n\n"
            "Для подтверждения отправьте:\n<code>/unbind confirm</code>"
        )
        return

    async with async_session() as session:
        group = await GroupRepository(session).get(group_id)
        if not group:
            await message.answer("❌ Группа уже отвязана.")
            return
        title = group.title
        ok = await GroupRepository(session).unbind_group(group_id)

    if not ok:
        await message.answer("❌ Не удалось отвязать группу.")
        return

    await message.answer(
        f"✅ Группа <b>{title}</b> отвязана.\n\n"
        "Для повторной привязки используйте /bind"
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


@router.message(Command("zero"))
async def cmd_zero(message: Message, command: CommandObject) -> None:
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
        users = await UserRepository(session).get_zero_activity(group_id, period)
    label = format_duration(period)
    await message.answer(
        format_zero_activity_list(users, period, f"👤 0 активности, в группе ≥{label}")
    )


@router.message(Command("cleanzero"))
async def cmd_cleanzero(message: Message, command: CommandObject, bot: Bot) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    args = command_args(message, command)
    if not args:
        await message.answer(
            "Использование:\n"
            "<code>/cleanzero 30d preview</code>\n"
            "<code>/cleanzero 30d confirm</code>"
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
            users = await service.preview_zero(group_id, period)
            await message.answer(
                format_zero_activity_list(users, period, f"👁 На кик (0 активности, ≥{label})")
            )
            return

        result = await service.execute_zero(group_id, period)

    lines = [
        f"🧹 <b>Кик завершён</b> (0 активности, в группе ≥{label})\n",
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
        logger.warning("Cleanzero report to group failed: %s", exc)


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


@router.message(Command("parsemembers"))
async def cmd_parsemembers(message: Message, bot: Bot) -> None:
    group_id = await ensure_admin(message)
    if not group_id:
        return
    status = await message.answer("⏳ Синхронизация участников с Telegram…")
    try:
        result = await MemberParseService(bot).parse_group(group_id)
        await status.edit_text(format_parse_result(result))
    except Exception as exc:
        logger.exception("parsemembers failed for %s: %s", group_id, exc)
        await status.edit_text("❌ Не удалось синхронизировать участников. Проверьте права бота в группе.")


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(BOT_COMMANDS)
