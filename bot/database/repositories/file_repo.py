"""
Repository: all MongoDB operations for the 'files' collection.
Covers CRUD + tag search + share code + dedup + rename.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from bot.models.file_record import FileRecord, generate_share_code

logger = logging.getLogger(__name__)
COL = "files"


class FileRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.col = db[COL]

    # ── Create ────────────────────────────────────────────────────────────────

    async def insert(self, record: FileRecord) -> str:
        doc = record.to_mongo()
        result = await self.col.insert_one(doc)
        return str(result.inserted_id)

    # ── Duplicate detection ───────────────────────────────────────────────────

    async def find_duplicate(
        self, user_id: int, file_unique_id: str
    ) -> Optional[FileRecord]:
        """
        Check if user already uploaded this exact file.
        Uses telegram_file_unique_id which is stable across bots/sessions.
        """
        doc = await self.col.find_one(
            {"user_id": user_id, "telegram_file_unique_id": file_unique_id}
        )
        return FileRecord(**doc) if doc else None

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_by_id(self, record_id: str) -> Optional[FileRecord]:
        if not ObjectId.is_valid(record_id):
            return None
        doc = await self.col.find_one({"_id": ObjectId(record_id)})
        return FileRecord(**doc) if doc else None

    async def get_by_share_code(self, code: str) -> Optional[FileRecord]:
        doc = await self.col.find_one({"share_code": code.upper()})
        return FileRecord(**doc) if doc else None

    async def list_by_user(
        self, user_id: int, page: int = 1, page_size: int = 8
    ) -> list[FileRecord]:
        skip = (page - 1) * page_size
        cursor = (
            self.col.find({"user_id": user_id})
            .sort("upload_date", -1)
            .skip(skip)
            .limit(page_size)
        )
        return [FileRecord(**d) for d in await cursor.to_list(page_size)]

    async def count_by_user(self, user_id: int) -> int:
        return await self.col.count_documents({"user_id": user_id})

    async def search_by_filename(
        self, user_id: int, query: str
    ) -> list[FileRecord]:
        cursor = self.col.find(
            {"user_id": user_id, "original_filename": {"$regex": query, "$options": "i"}}
        ).sort("upload_date", -1).limit(20)
        return [FileRecord(**d) for d in await cursor.to_list(20)]

    async def search_by_tag(
        self, user_id: int, tag: str
    ) -> list[FileRecord]:
        """Return all files for a user that carry the given tag (exact match)."""
        cursor = self.col.find(
            {"user_id": user_id, "tags": tag.lower().lstrip("#")}
        ).sort("upload_date", -1).limit(50)
        return [FileRecord(**d) for d in await cursor.to_list(50)]

    # ── Update ────────────────────────────────────────────────────────────────

    async def rename(
        self, record_id: str, user_id: int, new_name: str
    ) -> bool:
        """Set display_name without touching original_filename."""
        if not ObjectId.is_valid(record_id):
            return False
        result = await self.col.update_one(
            {"_id": ObjectId(record_id), "user_id": user_id},
            {"$set": {"display_name": new_name}},
        )
        return result.modified_count > 0

    async def set_tags(
        self, record_id: str, user_id: int, tags: list[str]
    ) -> bool:
        if not ObjectId.is_valid(record_id):
            return False
        result = await self.col.update_one(
            {"_id": ObjectId(record_id), "user_id": user_id},
            {"$set": {"tags": [t.lower().lstrip("#") for t in tags]}},
        )
        return result.modified_count > 0

    async def set_expiry(
        self, record_id: str, user_id: int, expires_at: Optional[datetime]
    ) -> bool:
        if not ObjectId.is_valid(record_id):
            return False
        update = (
            {"$set": {"expires_at": expires_at}}
            if expires_at
            else {"$unset": {"expires_at": ""}}
        )
        result = await self.col.update_one(
            {"_id": ObjectId(record_id), "user_id": user_id}, update
        )
        return result.modified_count > 0

    async def create_or_get_share_code(
        self, record_id: str, user_id: int
    ) -> Optional[str]:
        """
        Generate a unique share code for a file.
        If one already exists, return it as-is.
        """
        record = await self.get_by_id(record_id)
        if not record or record.user_id != user_id:
            return None
        if record.share_code:
            return record.share_code

        # Generate a collision-free code
        for _ in range(10):
            code = generate_share_code()
            existing = await self.col.find_one({"share_code": code})
            if not existing:
                await self.col.update_one(
                    {"_id": ObjectId(record_id)},
                    {"$set": {"share_code": code}},
                )
                return code
        return None  # Very unlikely collision exhaustion

    async def increment_share_uses(self, record_id: str) -> None:
        if ObjectId.is_valid(record_id):
            await self.col.update_one(
                {"_id": ObjectId(record_id)},
                {"$inc": {"share_code_uses": 1}},
            )

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_by_id(self, record_id: str, user_id: int) -> bool:
        if not ObjectId.is_valid(record_id):
            return False
        result = await self.col.delete_one(
            {"_id": ObjectId(record_id), "user_id": user_id}
        )
        return result.deleted_count > 0

    # ── Admin ─────────────────────────────────────────────────────────────────

    async def total_file_count(self) -> int:
        return await self.col.count_documents({})

    async def total_storage_bytes(self) -> int:
        pipeline = [{"$group": {"_id": None, "total": {"$sum": "$file_size"}}}]
        result = await self.col.aggregate(pipeline).to_list(1)
        return result[0]["total"] if result else 0

    async def distinct_user_count(self) -> int:
        return len(await self.col.distinct("user_id"))

    async def files_expiring_soon(self, within_hours: int = 24) -> list[FileRecord]:
        """Files expiring within the next N hours (for warning notifications)."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=within_hours)
        cursor = self.col.find(
            {"expires_at": {"$gte": now, "$lte": cutoff}}
        )
        return [FileRecord(**d) for d in await cursor.to_list(200)]
