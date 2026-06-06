from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import settings
from bot.database.engine import async_session
from bot.database.repository import AdminRepository, GroupRepository


class AdminContextMiddleware(BaseMiddleware):
  async def __call__(
      self,
      handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
      event: TelegramObject,
      data: dict[str, Any],
  ) -> Any:
      user = data.get("event_from_user")
      if user:
          data["is_global_owner"] = user.id == settings.owner_id
      return await handler(event, data)


async def require_group_admin(group_id: int, user_id: int) -> bool:
    if user_id == settings.owner_id:
        return True
    async with async_session() as session:
        admins = AdminRepository(session)
        return await admins.is_admin(group_id, user_id)


async def require_group_owner(group_id: int, user_id: int) -> bool:
    if user_id == settings.owner_id:
        return True
    async with async_session() as session:
        admins = AdminRepository(session)
        return await admins.is_owner(group_id, user_id)


async def get_user_groups(user_id: int):
    async with async_session() as session:
        groups = GroupRepository(session)
        return await groups.get_user_groups(user_id)
