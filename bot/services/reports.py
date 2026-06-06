from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repository import UserRepository, utcnow
from bot.utils.duration import format_duration


def format_user_line(user, index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else ""
    username = f"@{user.username}" if user.username else "—"
    last = user.last_activity.strftime("%d.%m.%Y")
    return (
        f"{prefix}<b>{user.first_name}</b> ({username})\n"
        f"   💬 {user.messages_count} | 👍 {user.reactions_count} | 🕐 {last}"
    )


def format_stats(stats: dict) -> str:
    return (
        "📊 <b>Статистика группы</b>\n\n"
        f"👥 Всего участников: <b>{stats['total']}</b>\n"
        f"🟢 Активных за 7 дней: <b>{stats['active_7']}</b>\n"
        f"🟢 Активных за 30 дней: <b>{stats['active_30']}</b>\n"
        f"🔴 Неактивных: <b>{stats['inactive']}</b>\n"
        f"🆕 Новых за неделю: <b>{stats['new_week']}</b>"
    )


def format_zero_activity_list(
    users: list,
    membership_period: timedelta | int,
    title: str | None = None,
) -> str:
    label = (
        format_duration(timedelta(days=membership_period))
        if isinstance(membership_period, int)
        else format_duration(membership_period)
    )
    header = title or f"👤 В группе ≥{label}, 0 сообщений и 0 реакций"
    if not users:
        return f"{header}\n\n✅ Таких участников не найдено."
    lines = [f"{header}\n", f"Найдено: <b>{len(users)}</b>\n"]
    for i, u in enumerate(users[:30], 1):
        joined = u.join_date.strftime("%d.%m.%Y")
        lines.append(
            f"{i}. <b>{u.first_name}</b> (@{u.username or '—'})\n"
            f"   💬 0 | 👍 0 | 📅 в базе с {joined}"
        )
    if len(users) > 30:
        lines.append(f"\n... и ещё {len(users) - 30}")
    return "\n".join(lines)


def format_inactive_list(
    users: list,
    period: timedelta | int,
    title: str | None = None,
) -> str:
    label = format_duration(timedelta(days=period)) if isinstance(period, int) else format_duration(period)
    header = title or f"👥 Неактивные более {label}"
    if not users:
        return f"{header}\n\n✅ Неактивных не найдено."
    lines = [f"{header}\n", f"Найдено: <b>{len(users)}</b>\n"]
    for i, u in enumerate(users[:30], 1):
        lines.append(format_user_line(u, i))
    if len(users) > 30:
        lines.append(f"\n... и ещё {len(users) - 30}")
    return "\n".join(lines)


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)

    async def weekly(self, group_id: int) -> str:
        since = utcnow() - timedelta(days=7)
        stats = await self.users.get_stats(group_id)
        top = await self.users.get_top_active(group_id, 5)
        removed = await self.users.get_removed_since(group_id, since)

        lines = [
            "📅 <b>Еженедельный отчёт</b>\n",
            format_stats(stats),
            "\n🔥 <b>Самые активные:</b>",
        ]
        if top:
            lines.extend(format_user_line(u, i) for i, u in enumerate(top, 1))
        else:
            lines.append("— нет данных —")

        lines.append("\n🗑 <b>Удалённые за неделю:</b>")
        if removed:
            for i, r in enumerate(removed[:10], 1):
                username = f"@{r.username}" if r.username else "—"
                lines.append(f"{i}. {r.first_name} ({username})")
        else:
            lines.append("— нет —")

        return "\n".join(lines)

    async def monthly(self, group_id: int) -> str:
        since = utcnow() - timedelta(days=30)
        stats = await self.users.get_stats(group_id)
        top = await self.users.get_top_active(group_id, 10)
        removed = await self.users.get_removed_since(group_id, since)

        lines = [
            "📆 <b>Ежемесячный отчёт</b>\n",
            format_stats(stats),
            "\n🔥 <b>Топ активных за месяц:</b>",
        ]
        if top:
            lines.extend(format_user_line(u, i) for i, u in enumerate(top, 1))
        else:
            lines.append("— нет данных —")

        total_messages = sum(u.messages_count for u in top)
        lines.append(f"\n💬 Сообщений у топ-10: <b>{total_messages}</b>")

        lines.append("\n🗑 <b>Удалённые за месяц:</b>")
        if removed:
            lines.append(f"Всего: <b>{len(removed)}</b>")
            for i, r in enumerate(removed[:15], 1):
                username = f"@{r.username}" if r.username else "—"
                lines.append(f"{i}. {r.first_name} ({username})")
        else:
            lines.append("— нет —")

        return "\n".join(lines)
