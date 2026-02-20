#!/usr/bin/env python3
"""
Migration script: Migrate existing quota data from storage tracking to download tracking.

This script:
1. Sets bandwidth_used = 0, download_count = 0 for all users
2. Sets bandwidth_limit = 500MB (default) and download_limit = 0 (unlimited)
3. Sets quota_reset_time to next midnight UTC
4. Removes old storage quota fields (used_bytes, quota_bytes, file_count)
5. Preserves download_token and token_verified_until

Run this script ONCE after deploying the download quota changes.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _get_next_midnight_utc() -> datetime:
    """Calculate next midnight UTC."""
    now = datetime.now(timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return tomorrow


async def migrate_quotas():
    """Migrate all user quota documents to download tracking."""
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name = os.getenv("MONGO_DB_NAME", "tg_file_storage")
    
    # Default download quota settings
    default_bandwidth_mb = int(os.getenv("DEFAULT_BANDWIDTH_LIMIT_MB", "500"))
    default_download_limit = int(os.getenv("DEFAULT_DOWNLOAD_LIMIT", "0"))
    
    print(f"Connecting to MongoDB at {mongo_uri}...")
    client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
    await client.admin.command("ping")
    db = client[mongo_db_name]
    print(f"Connected to database: {mongo_db_name}")
    
    quotas_col = db["user_quotas"]
    
    # Count existing documents
    total_count = await quotas_col.count_documents({})
    print(f"Found {total_count} user quota documents to migrate.")
    
    if total_count == 0:
        print("No documents to migrate. Done.")
        client.close()
        return
    
    next_midnight = _get_next_midnight_utc()
    
    # Migration update:
    # - Set new fields with default values
    # - Unset old storage quota fields
    result = await quotas_col.update_many(
        {},  # All documents
        {
            "$set": {
                "bandwidth_used": 0,
                "download_count": 0,
                "bandwidth_limit": default_bandwidth_mb * 1024 * 1024,
                "download_limit": default_download_limit,
                "quota_reset_time": next_midnight,
                "updated_at": datetime.now(timezone.utc),
            },
            "$unset": {
                "used_bytes": "",
                "quota_bytes": "",
                "file_count": "",
            },
        }
    )
    
    print(f"Migration complete!")
    print(f"  - Modified: {result.modified_count} documents")
    print(f"  - Default bandwidth limit: {default_bandwidth_mb} MB")
    print(f"  - Default download limit: {default_download_limit if default_download_limit > 0 else 'unlimited'}")
    print(f"  - Quota reset time: {next_midnight.isoformat()}")
    
    # Verify migration
    print("\nVerifying migration...")
    sample = await quotas_col.find_one({})
    if sample:
        print(f"Sample document fields: {list(sample.keys())}")
        if "used_bytes" in sample:
            print("  WARNING: 'used_bytes' still present!")
        if "quota_bytes" in sample:
            print("  WARNING: 'quota_bytes' still present!")
        if "file_count" in sample:
            print("  WARNING: 'file_count' still present!")
        if "bandwidth_used" in sample:
            print(f"  ✓ 'bandwidth_used' = {sample['bandwidth_used']}")
        if "download_count" in sample:
            print(f"  ✓ 'download_count' = {sample['download_count']}")
        if "bandwidth_limit" in sample:
            print(f"  ✓ 'bandwidth_limit' = {sample['bandwidth_limit']}")
        if "download_token" in sample:
            print(f"  ✓ 'download_token' preserved")
        if "token_verified_until" in sample:
            print(f"  ✓ 'token_verified_until' preserved")
    
    client.close()
    print("\nDone.")


if __name__ == "__main__":
    print("=" * 60)
    print("Storage Quota → Download Quota Migration")
    print("=" * 60)
    print()
    
    asyncio.run(migrate_quotas())
