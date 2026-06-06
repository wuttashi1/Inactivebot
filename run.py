"""Запуск бота: python run.py (из корня проекта)."""
from bot.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
