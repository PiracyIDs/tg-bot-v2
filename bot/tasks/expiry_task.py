"""
Background task: warn users about files expiring in the next 24 hours.
Runs on a configurable interval via asyncio.

MongoDB's native TTL index handles the actual deletion automatically
(set via the 'expires_at' field + expireAfterSeconds=0 index).
This task only sends user-facing warning notifications.
"""
import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot

from bot.config import settings
from bot.database.connection import get_db
from bot.database.repositories.file_repo import FileRepository
from bot.utils.file_utils import format_size

logger = logging.getLogger(__name__)


async def expiry_warning_task(bot: Bot) -> None:
    """
    Loop forever, sleeping between scans.
    On each iteration, find files expiring in 24 hours and DM their owners.
    """
    logger.info(
        "Expiry warning task started (interval=%ss)", settings.expiry_cleanup_interval
    )
    while True:
        await asyncio.sleep(settings.expiry_cleanup_interval)
        try:
            await _run_expiry_warnings(bot)
        except Exception as exc:
            logger.exception("Expiry warning task error: %s", exc)


async def _run_expiry_warnings(bot: Bot) -> None:
    repo = FileRepository(get_db())
    expiring = await repo.files_expiring_soon(within_hours=24)

    if not expiring:
        return

    logger.info("Found %d files expiring within 24h", len(expiring))

    # Group by user so each user gets one DM with all their expiring files
    by_user: dict[int, list] = {}
    for record in expiring:
        by_user.setdefault(record.user_id, []).append(record)

    for user_id, records in by_user.items():
        lines = [f"⏰ <b>{len(records)} file(s) expiring in less than 24 hours:</b>\n"]
        for rec in records:
            exp_str = rec.expires_at.strftime("%Y-%m-%d %H:%M UTC") if rec.expires_at else "?"
            lines.append(
                f"• <b>{rec.effective_name}</b> ({format_size(rec.file_size)})\n"
                f"  Expires: {exp_str}\n"
                f"  /get <code>{rec.id}</code> to save it\n"
            )
        try:
            await bot.send_message(user_id, "\n".join(lines), parse_mode="HTML")
        except Exception as exc:
            logger.warning("Could not notify user %s: %s", user_id, exc)
