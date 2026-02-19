"""
Repository: per-user storage quota tracking.
Collection: 'user_quotas'
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from bot.config import settings
from bot.models.file_record import UserQuotaRecord

logger = logging.getLogger(__name__)
COL = "user_quotas"


class QuotaRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db[COL]

    async def _get_or_create(self, user_id: int) -> UserQuotaRecord:
        doc = await self.col.find_one({"user_id": user_id})
        if doc:
            return UserQuotaRecord(**doc)
        # First time — create with default quota from config
        new = UserQuotaRecord(
            user_id=user_id,
            quota_bytes=settings.default_quota_mb * 1024 * 1024,
        )
        await self.col.insert_one(new.to_mongo())
        return new

    async def get(self, user_id: int) -> UserQuotaRecord:
        return await self._get_or_create(user_id)

    async def can_upload(self, user_id: int, file_size: int) -> tuple[bool, UserQuotaRecord]:
        """
        Returns (allowed, quota_record).
        Allowed is always True when quota is unlimited (quota_bytes == 0).
        """
        quota = await self._get_or_create(user_id)
        if quota.is_unlimited:
            return True, quota
        return quota.remaining_bytes >= file_size, quota

    async def add_usage(self, user_id: int, file_size: int) -> None:
        """Increment used_bytes and file_count atomically."""
        await self.col.update_one(
            {"user_id": user_id},
            {
                "$inc": {"used_bytes": file_size, "file_count": 1},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )

    async def remove_usage(self, user_id: int, file_size: int) -> None:
        """Decrement used_bytes and file_count (floor at 0)."""
        quota = await self._get_or_create(user_id)
        new_used = max(0, quota.used_bytes - file_size)
        new_count = max(0, quota.file_count - 1)
        await self.col.update_one(
            {"user_id": user_id},
            {"$set": {
                "used_bytes": new_used,
                "file_count": new_count,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def set_quota(self, user_id: int, quota_mb: int) -> None:
        """Admin: set a custom quota in MB. 0 = unlimited."""
        await self.col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "quota_bytes": quota_mb * 1024 * 1024,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def all_quotas(self) -> list[UserQuotaRecord]:
        """Admin: list all user quota records."""
        cursor = self.col.find({}).sort("used_bytes", -1)
        return [UserQuotaRecord(**d) for d in await cursor.to_list(500)]
