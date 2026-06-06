from aiogram import Router

from bot.handlers.commands import router as commands_router
from bot.handlers.group_events import router as group_router
from bot.handlers.panel import router as panel_router
from bot.handlers.start import router as start_router
from bot.handlers.user_actions import router as user_router


def setup_routers() -> Router:
    root = Router()
    root.include_router(commands_router)
    root.include_router(start_router)
    root.include_router(panel_router)
    root.include_router(user_router)
    root.include_router(group_router)
    return root
