"""
Central configuration using Pydantic Settings.
Reads from environment variables / .env file automatically.

IMPORTANT — lazy singleton pattern
───────────────────────────────────
Settings() is NOT instantiated at import time.
Use the module-level `settings` proxy object, which loads lazily on first
attribute access.  This means:
  • Importing `bot.config` never fails even if .env is missing.
  • The real validation runs once, the first time any value is read.
  • Tests can monkeypatch env vars before the first access.
"""
from __future__ import annotations
import pathlib
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file so the bot works regardless of the
# current working directory when launched.
_ENV_FILE = pathlib.Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Accept both project-root .env and the resolved absolute path
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Telegram ──────────────────────────────────────────────────────────────
    bot_token: str
    storage_channel_id: int          # e.g. -1001234567890

    # ── MongoDB ───────────────────────────────────────────────────────────────
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "tg_file_storage"

    # ── Security / Access ─────────────────────────────────────────────────────
    allowed_user_ids: list[int] = []  # Empty = open access
    admin_user_ids: list[int] = []    # Users with /admin access

    # ── Quota ─────────────────────────────────────────────────────────────────
    default_quota_mb: int = 500       # Per-user default quota in MB (0 = unlimited)

    # ── Auto-Expiry ───────────────────────────────────────────────────────────
    default_expiry_days: int = 0      # 0 = never expires
    expiry_cleanup_interval: int = 3600  # Run cleanup every N seconds (1 hour)

    # ── App ───────────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    max_file_size_mb: int = 50

    @field_validator("allowed_user_ids", "admin_user_ids", mode="before")
    @classmethod
    def parse_id_list(cls, v):
        """Allow comma-separated string from .env: '111,222,333'"""
        if isinstance(v, str):
            return [int(uid.strip()) for uid in v.split(",") if uid.strip()]
        return v or []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Cached settings loader — called once, then returns the same object.
    Using @lru_cache means the .env file is only read once per process.
    """
    return Settings()


# Convenience proxy — `from bot.config import settings` still works everywhere.
# Attribute access on this object delegates to the real Settings instance,
# loading it lazily on first use.
class _SettingsProxy:
    """Thin proxy that defers Settings() construction until first use."""
    __slots__ = ()

    def __getattr__(self, name: str):
        return getattr(get_settings(), name)

    def __repr__(self) -> str:
        return repr(get_settings())


settings: Settings = _SettingsProxy()  # type: ignore[assignment]
