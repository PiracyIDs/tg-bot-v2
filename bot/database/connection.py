"""
Motor async MongoDB client — lifecycle + index management.
"""
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from bot.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    global _client, _db
    logger.info("Connecting to MongoDB at %s", settings.mongo_uri)
    _client = AsyncIOMotorClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    await _client.admin.command("ping")
    _db = _client[settings.mongo_db_name]
    logger.info("MongoDB connected — db: '%s'", settings.mongo_db_name)
    await _ensure_indexes()


async def _ensure_indexes() -> None:
    # ── files collection ──────────────────────────────────────────────────────
    files = _db["files"]
    await files.create_index([("user_id", ASCENDING), ("upload_date", DESCENDING)])
    await files.create_index(
        [("internal_message_id", ASCENDING), ("channel_id", ASCENDING)],
        unique=True,
    )
    # Dedup index on the stable Telegram unique ID
    await files.create_index([("user_id", ASCENDING), ("telegram_file_unique_id", ASCENDING)])
    # Tag search
    await files.create_index([("user_id", ASCENDING), ("tags", ASCENDING)])
    # Share code lookup
    await files.create_index("share_code", sparse=True, unique=True)
    # TTL index — MongoDB auto-deletes docs when expires_at is reached
    await files.create_index("expires_at", expireAfterSeconds=0, sparse=True)

    # ── user_quotas collection ────────────────────────────────────────────────
    quotas = _db["user_quotas"]
    await quotas.create_index("user_id", unique=True)

    logger.info("MongoDB indexes ensured.")


async def close_mongo() -> None:
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB connection closed.")


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialized. Call connect_to_mongo() first.")
    return _db
