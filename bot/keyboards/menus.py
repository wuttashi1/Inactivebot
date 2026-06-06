from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import (
    ActiveCb,
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
)
from bot.database.models import Group


class Keyboards:
    @staticmethod
    def setup() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔗 Привязать группу", callback_data=GroupCb(action="bind").pack())
        return builder.as_markup()

    @staticmethod
    def group_select(groups: list[Group]) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for g in groups:
            prefix = "⭐ " if g.is_primary else ""
            builder.button(
                text=f"{prefix}{g.title or g.group_id}",
                callback_data=GroupCb(action="select", group_id=g.group_id).pack(),
            )
        builder.button(text="🔗 Привязать новую", callback_data=GroupCb(action="bind").pack())
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def main_menu(group_id: int, is_owner: bool) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        buttons = [
            ("📊 Статистика", MenuCb(action="stats", group_id=group_id)),
            ("👥 Участники", MenuCb(action="members", group_id=group_id)),
            ("🧹 Очистка неактива", MenuCb(action="clean", group_id=group_id)),
            ("⚙️ Настройки", MenuCb(action="settings", group_id=group_id)),
            ("🛡 Админы", MenuCb(action="admins", group_id=group_id)),
            ("📋 Белый список", MenuCb(action="whitelist", group_id=group_id)),
            ("🔔 Автоочистка", MenuCb(action="autoclean", group_id=group_id)),
            ("📄 Отчёты", MenuCb(action="reports", group_id=group_id)),
            ("📣 Перекличка", MenuCb(action="rollcall", group_id=group_id)),
            ("⚠️ Уведомить неактивных", MenuCb(action="warn", group_id=group_id)),
        ]
        if is_owner:
            buttons.append(("👑 Панель владельца", MenuCb(action="owner", group_id=group_id)))
        for text, cb in buttons:
            builder.button(text=text, callback_data=cb.pack())
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def back(group_id: int, target: str = "main") -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action=target, group_id=group_id).pack())
        return builder.as_markup()

    @staticmethod
    def stats(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data=MenuCb(action="stats", group_id=group_id).pack())
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="main", group_id=group_id).pack())
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def members_menu(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        items = [
            ("🔥 Топ активных", MembersCb(action="top_active", group_id=group_id)),
            ("📉 Топ неактивных", MembersCb(action="top_inactive", group_id=group_id)),
            ("⚠️ Кандидаты на удаление", MembersCb(action="candidates", group_id=group_id, days=30)),
            ("⏳ Неактив 7д", MembersCb(action="inactive", group_id=group_id, days=7)),
            ("⏳ Неактив 14д", MembersCb(action="inactive", group_id=group_id, days=14)),
            ("⏳ Неактив 30д", MembersCb(action="inactive", group_id=group_id, days=30)),
            ("⏳ Неактив 60д", MembersCb(action="inactive", group_id=group_id, days=60)),
        ]
        for text, cb in items:
            builder.button(text=text, callback_data=cb.pack())
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="main", group_id=group_id).pack())
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def clean_periods(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for days in (7, 14, 30, 60):
            builder.button(
                text=f"⏳ {days} дней",
                callback_data=CleanCb(action="period", group_id=group_id, days=days).pack(),
            )
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="main", group_id=group_id).pack())
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def clean_confirm(group_id: int, days: int, count: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="👁 Просмотр списка",
            callback_data=CleanCb(action="preview", group_id=group_id, days=days).pack(),
        )
        if count > 0:
            builder.button(
                text="🧹 Удалить",
                callback_data=CleanCb(action="confirm", group_id=group_id, days=days).pack(),
            )
        builder.button(
            text="❌ Отмена",
            callback_data=CleanCb(action="cancel", group_id=group_id).pack(),
        )
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def settings_menu(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔔 Автоочистка", callback_data=MenuCb(action="autoclean", group_id=group_id).pack())
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="main", group_id=group_id).pack())
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def autoclean(group_id: int, enabled: bool, period_seconds: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🟢 Включить" if not enabled else "✅ Включено",
            callback_data=AutoCleanCb(action="toggle", group_id=group_id, enabled=1).pack(),
        )
        builder.button(
            text="🔴 Выключить" if enabled else "⛔ Выключено",
            callback_data=AutoCleanCb(action="toggle", group_id=group_id, enabled=0).pack(),
        )
        for d in (30, 60, 90):
            mark = "✓ " if period_seconds == d * 86400 else ""
            builder.button(
                text=f"{mark}⏱ {d} дней",
                callback_data=AutoCleanCb(action="period", group_id=group_id, days=d).pack(),
            )
        builder.button(
            text="✏️ Свой период",
            callback_data=AutoCleanCb(action="custom", group_id=group_id).pack(),
        )
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="settings", group_id=group_id).pack())
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def admins_menu(group_id: int, is_owner: bool) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        if is_owner:
            builder.button(text="➕ Добавить", callback_data=AdminCb(action="add", group_id=group_id).pack())
            builder.button(text="➖ Удалить", callback_data=AdminCb(action="remove", group_id=group_id).pack())
        builder.button(text="📋 Список", callback_data=AdminCb(action="list", group_id=group_id).pack())
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="main", group_id=group_id).pack())
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def whitelist_menu(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Добавить", callback_data=WhitelistCb(action="add", group_id=group_id).pack())
        builder.button(text="➖ Удалить", callback_data=WhitelistCb(action="remove", group_id=group_id).pack())
        builder.button(text="👀 Просмотр", callback_data=WhitelistCb(action="list", group_id=group_id).pack())
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="main", group_id=group_id).pack())
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def reports_menu(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="📅 Еженедельный", callback_data=ReportCb(action="weekly", group_id=group_id).pack())
        builder.button(text="📆 Ежемесячный", callback_data=ReportCb(action="monthly", group_id=group_id).pack())
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="main", group_id=group_id).pack())
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def warn_periods(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for days in (7, 14, 30, 60):
            builder.button(
                text=f"⏳ {days} дней",
                callback_data=WarnCb(action="period", group_id=group_id, days=days).pack(),
            )
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="main", group_id=group_id).pack())
        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def warn_confirm(group_id: int, days: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="📩 Отправить уведомления",
            callback_data=WarnCb(action="send", group_id=group_id, days=days).pack(),
        )
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="warn", group_id=group_id).pack())
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def owner_menu(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🗂 Все группы", callback_data=OwnerCb(action="groups", group_id=group_id).pack())
        builder.button(text="👤 Передать владельца", callback_data=OwnerCb(action="transfer", group_id=group_id).pack())
        builder.button(text="🧨 Полный сброс", callback_data=OwnerCb(action="reset", group_id=group_id).pack())
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="main", group_id=group_id).pack())
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def rollcall_confirm(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="📣 Запустить перекличку", callback_data=RollcallCb(action="start", group_id=group_id).pack())
        builder.button(text="⬅️ Назад", callback_data=MenuCb(action="main", group_id=group_id).pack())
        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    def rollcall_user(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(
            text="✅ Подтвердить активность",
            callback_data=RollcallCb(action="confirm", group_id=group_id).pack(),
        )
        return builder.as_markup()

    @staticmethod
    def i_am_active(group_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Я активен", callback_data=ActiveCb(group_id=group_id).pack())
        return builder.as_markup()


keyboards = Keyboards()
