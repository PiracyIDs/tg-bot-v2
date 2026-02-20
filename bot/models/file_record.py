"""
Pydantic models for all MongoDB documents.
- FileRecord      : one stored file (enhanced with tags, expiry, share code)
- UserQuotaRecord : tracks per-user download quota
- ShareCode       : maps a short code to a file record
"""
from __future__ import annotations
import secrets
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId


# ── ObjectId helper ───────────────────────────────────────────────────────────

class PyObjectId(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, _info=None):
        if not ObjectId.is_valid(v):
            raise ValueError(f"Invalid ObjectId: {v}")
        return str(v)


# ── File Record ───────────────────────────────────────────────────────────────

class FileRecord(BaseModel):
    """
    Represents one stored file.
    Collection: 'files'
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    # Owner
    user_id: int
    username: Optional[str] = None

    # File identity
    original_filename: str
    file_type: str                   # document / photo / video / audio / voice …
    mime_type: Optional[str] = None
    file_size: Optional[int] = None  # Bytes

    # Telegram storage pointers
    internal_message_id: int         # message_id inside the storage channel
    channel_id: int
    telegram_file_id: str            # May rotate; message_id is the stable ref
    telegram_file_unique_id: str     # Stable across bots — used for dedup

    # User-facing metadata
    caption: Optional[str] = None
    tags: list[str] = Field(default_factory=list)   # e.g. ["invoice", "2024"]
    display_name: Optional[str] = None              # Renamed display name

    # Share
    share_code: Optional[str] = None                # Short alphanumeric code
    share_code_uses: int = 0                         # How many times it was used

    # Expiry
    expires_at: Optional[datetime] = None           # None = never

    # Timestamps
    upload_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        if "_id" in data:
            data["_id"] = ObjectId(data["_id"])
        return data

    @property
    def effective_name(self) -> str:
        """Display name falls back to original filename."""
        return self.display_name or self.original_filename


# ── User Quota Record ─────────────────────────────────────────────────────────

class UserQuotaRecord(BaseModel):
    """
    Tracks a single user's download quota.
    Collection: 'user_quotas'
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    user_id: int
    bandwidth_used: int = 0          # Total bandwidth used (bytes)
    bandwidth_limit: int             # Bandwidth limit (0 = unlimited)
    download_count: int = 0          # Number of downloads
    download_limit: int = 0          # Download limit (0 = unlimited)
    quota_reset_time: Optional[datetime] = None  # Next reset time
    download_token: Optional[str] = None  # Token required for non-admin downloads
    token_verified_until: Optional[datetime] = None  # Token verification expiry
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    @property
    def is_unlimited(self) -> bool:
        return self.bandwidth_limit == 0

    @property
    def bandwidth_remaining(self) -> float:
        """Returns remaining bandwidth (inf if unlimited)."""
        if self.is_unlimited:
            return float("inf")
        return max(0, self.bandwidth_limit - self.bandwidth_used)

    @property
    def downloads_remaining(self) -> float:
        """Returns remaining downloads (inf if unlimited)."""
        if self.download_limit == 0:
            return float("inf")
        return max(0, self.download_limit - self.download_count)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        if "_id" in data:
            data["_id"] = ObjectId(data["_id"])
        return data


# ── Share Code (thin document) ────────────────────────────────────────────────

def generate_share_code(length: int = 8) -> str:
    """Generate a URL-safe random share code."""
    return secrets.token_urlsafe(length)[:length].upper()
