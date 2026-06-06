from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Admin, BotState, CleanupBackup, Group, User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, group_id: int) -> Group | None:
        return await self.session.get(Group, group_id)

    async def get_user_groups(self, user_id: int) -> list[Group]:
        stmt = (
            select(Group)
            .join(Admin, Admin.group_id == Group.group_id)
            .where(Admin.user_id == user_id)
            .order_by(Group.is_primary.desc(), Group.title)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def bind_group(self, group_id: int, title: str, owner_id: int) -> Group:
        stmt = insert(Group).values(
            group_id=group_id,
            title=title,
            owner_id=owner_id,
            is_primary=True,
        ).on_conflict_do_update(
            index_elements=["group_id"],
            set_={"title": title},
        )
        await self.session.execute(stmt)

        admin_stmt = insert(Admin).values(
            group_id=group_id,
            user_id=owner_id,
            role="owner",
        ).on_conflict_do_nothing()
        await self.session.execute(admin_stmt)

        await self.session.execute(
            update(Group).where(Group.group_id != group_id, Group.owner_id == owner_id).values(is_primary=False)
        )
        await self.session.commit()
        group = await self.get(group_id)
        assert group is not None
        return group

    async def set_autoclean(
        self,
        group_id: int,
        enabled: bool,
        period: timedelta | int | None = None,
    ) -> None:
        values: dict = {"autoclean_enabled": enabled}
        if period is not None:
            if isinstance(period, int):
                td = timedelta(days=period)
            else:
                td = period
            seconds = int(td.total_seconds())
            values["autoclean_interval_seconds"] = seconds
            values["autoclean_days"] = max(1, seconds // 86400)
        await self.session.execute(update(Group).where(Group.group_id == group_id).values(**values))
        await self.session.commit()

    @staticmethod
    def autoclean_period(group: Group) -> timedelta:
        if group.autoclean_interval_seconds:
            return timedelta(seconds=group.autoclean_interval_seconds)
        return timedelta(days=group.autoclean_days)

    async def get_autoclean_groups(self) -> list[Group]:
        stmt = select(Group).where(Group.autoclean_enabled.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_bound(self) -> list[Group]:
        stmt = select(Group).order_by(Group.title)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def transfer_owner(self, group_id: int, old_owner_id: int, new_owner_id: int) -> None:
        await self.session.execute(
            update(Group).where(Group.group_id == group_id).values(owner_id=new_owner_id)
        )
        await self.session.execute(
            update(Admin).where(Admin.group_id == group_id, Admin.user_id == old_owner_id).values(role="admin")
        )
        stmt = insert(Admin).values(
            group_id=group_id,
            user_id=new_owner_id,
            role="owner",
        ).on_conflict_do_update(
            index_elements=["group_id", "user_id"],
            set_={"role": "owner"},
        )
        await self.session.execute(stmt)
        await self.session.commit()


class AdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def is_admin(self, group_id: int, user_id: int) -> bool:
        stmt = select(Admin).where(Admin.group_id == group_id, Admin.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def is_owner(self, group_id: int, user_id: int) -> bool:
        stmt = select(Admin).where(
            Admin.group_id == group_id,
            Admin.user_id == user_id,
            Admin.role == "owner",
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_role(self, group_id: int, user_id: int) -> str | None:
        stmt = select(Admin.role).where(Admin.group_id == group_id, Admin.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_admins(self, group_id: int) -> list[Admin]:
        stmt = select(Admin).where(Admin.group_id == group_id).order_by(Admin.role, Admin.user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_admin(self, group_id: int, user_id: int, role: str = "admin") -> None:
        stmt = insert(Admin).values(group_id=group_id, user_id=user_id, role=role).on_conflict_do_nothing()
        await self.session.execute(stmt)
        await self.session.commit()

    async def remove_admin(self, group_id: int, user_id: int) -> bool:
        stmt = delete(Admin).where(
            Admin.group_id == group_id,
            Admin.user_id == user_id,
            Admin.role != "owner",
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_member(
        self,
        group_id: int,
        user_id: int,
        username: str | None,
        first_name: str,
    ) -> User:
        now = utcnow()
        stmt = insert(User).values(
            group_id=group_id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            join_date=now,
            last_activity=now,
        ).on_conflict_do_update(
            index_elements=["group_id", "user_id"],
            set_={
                "username": username,
                "first_name": first_name,
                "is_active": True,
            },
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return await self.get_user(group_id, user_id)

    async def get_user(self, group_id: int, user_id: int) -> User | None:
        stmt = select(User).where(User.group_id == group_id, User.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def record_message(self, group_id: int, user_id: int, username: str | None, first_name: str) -> None:
        now = utcnow()
        stmt = insert(User).values(
            group_id=group_id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            join_date=now,
            last_activity=now,
            messages_count=1,
        ).on_conflict_do_update(
            index_elements=["group_id", "user_id"],
            set_={
                "username": username,
                "first_name": first_name,
                "last_activity": now,
                "messages_count": User.messages_count + 1,
                "is_active": True,
            },
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def record_reaction(self, group_id: int, user_id: int, username: str | None, first_name: str) -> None:
        now = utcnow()
        stmt = insert(User).values(
            group_id=group_id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            join_date=now,
            last_activity=now,
            reactions_count=1,
        ).on_conflict_do_update(
            index_elements=["group_id", "user_id"],
            set_={
                "username": username,
                "first_name": first_name,
                "last_activity": now,
                "reactions_count": User.reactions_count + 1,
                "is_active": True,
            },
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def touch_activity(self, group_id: int, user_id: int) -> None:
        await self.session.execute(
            update(User)
            .where(User.group_id == group_id, User.user_id == user_id)
            .values(last_activity=utcnow(), is_active=True)
        )
        await self.session.commit()

    async def get_stats(self, group_id: int) -> dict:
        now = utcnow()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        total = await self.session.scalar(
            select(func.count()).select_from(User).where(User.group_id == group_id, User.is_active.is_(True))
        )
        active_7 = await self.session.scalar(
            select(func.count()).select_from(User).where(
                User.group_id == group_id,
                User.is_active.is_(True),
                User.last_activity >= week_ago,
            )
        )
        active_30 = await self.session.scalar(
            select(func.count()).select_from(User).where(
                User.group_id == group_id,
                User.is_active.is_(True),
                User.last_activity >= month_ago,
            )
        )
        new_week = await self.session.scalar(
            select(func.count()).select_from(User).where(
                User.group_id == group_id,
                User.join_date >= week_ago,
            )
        )
        inactive = (total or 0) - (active_30 or 0)
        return {
            "total": total or 0,
            "active_7": active_7 or 0,
            "active_30": active_30 or 0,
            "inactive": max(inactive, 0),
            "new_week": new_week or 0,
        }

    async def get_inactive(
        self,
        group_id: int,
        period: timedelta | int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        td = timedelta(days=period) if isinstance(period, int) else period
        cutoff = utcnow() - td
        stmt = (
            select(User)
            .where(
                User.group_id == group_id,
                User.is_active.is_(True),
                User.whitelisted.is_(False),
                User.last_activity < cutoff,
            )
            .order_by(User.last_activity)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_inactive(self, group_id: int, period: timedelta | int) -> int:
        td = timedelta(days=period) if isinstance(period, int) else period
        cutoff = utcnow() - td
        count = await self.session.scalar(
            select(func.count()).select_from(User).where(
                User.group_id == group_id,
                User.is_active.is_(True),
                User.whitelisted.is_(False),
                User.last_activity < cutoff,
            )
        )
        return count or 0

    async def get_top_active(self, group_id: int, limit: int = 10) -> list[User]:
        stmt = (
            select(User)
            .where(User.group_id == group_id, User.is_active.is_(True))
            .order_by(User.messages_count.desc(), User.reactions_count.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_top_inactive(self, group_id: int, limit: int = 10) -> list[User]:
        stmt = (
            select(User)
            .where(User.group_id == group_id, User.is_active.is_(True))
            .order_by(User.last_activity)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_whitelist(self, group_id: int, user_id: int, value: bool) -> bool:
        result = await self.session.execute(
            update(User)
            .where(User.group_id == group_id, User.user_id == user_id)
            .values(whitelisted=value)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def list_whitelist(self, group_id: int) -> list[User]:
        stmt = select(User).where(User.group_id == group_id, User.whitelisted.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_username(self, group_id: int, username: str) -> User | None:
        clean = username.lstrip("@").lower()
        stmt = select(User).where(
            User.group_id == group_id,
            func.lower(User.username) == clean,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_removed(self, group_id: int, user_id: int) -> None:
        await self.session.execute(
            update(User).where(User.group_id == group_id, User.user_id == user_id).values(is_active=False)
        )
        await self.session.commit()

    async def get_removed_since(self, group_id: int, since: datetime) -> list[CleanupBackup]:
        stmt = select(CleanupBackup).where(
            CleanupBackup.group_id == group_id,
            CleanupBackup.removed_at >= since,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_cleanup_backup(self, group_id: int, user: User, reason: str = "inactive") -> None:
        backup = CleanupBackup(
            group_id=group_id,
            user_id=user.user_id,
            username=user.username,
            first_name=user.first_name,
            reason=reason,
        )
        self.session.add(backup)
        await self.session.commit()

    async def list_active_users(self, group_id: int) -> list[User]:
        stmt = select(User).where(User.group_id == group_id, User.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class BotStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self) -> BotState:
        state = await self.session.get(BotState, 1)
        if state is None:
            state = BotState(id=1)
            self.session.add(state)
            await self.session.commit()
        return state

    async def record_shutdown(self) -> None:
        state = await self.get()
        state.last_shutdown_at = utcnow()
        await self.session.commit()

    async def record_startup(self) -> BotState:
        state = await self.get()
        state.last_startup_at = utcnow()
        await self.session.commit()
        return state

    async def save_last_update_id(self, update_id: int) -> None:
        state = await self.get()
        state.last_update_id = update_id
        await self.session.commit()

    async def get_last_update_id(self) -> int | None:
        state = await self.get()
        return state.last_update_id
