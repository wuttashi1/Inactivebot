from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    owner_id: int
    database_url: str = "postgresql+asyncpg://activity:activity@localhost:5432/activity_bot"
    log_level: str = "INFO"
    log_dir: str = str(_ROOT / "logs")


settings = Settings()
