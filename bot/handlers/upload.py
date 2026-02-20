"""
Upload handler — with duplicate detection.
Note: Storage quota removed; now using download quota system.
"""
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.types import Message

from bot.config import settings
from bot.database.connection import get_db
from bot.database.repositories.file_repo import FileRepository
from bot.models.file_record import FileRecord
from bot.utils.file_utils import detect_file_type, extract_file_info, format_size
from bot.utils.keyboards import build_file_action_keyboard

logger = logging.getLogger(__name__)
router = Router(name="upload")

MEDIA_FILTER = (
    F.document | F.photo | F.video | F.audio
    | F.voice | F.video_note | F.sticker | F.animation
)


def is_admin(user_id: int) -> bool:
    """Check if user is an admin."""
    return user_id in settings.admin_user_ids


@router.message(MEDIA_FILTER)
async def handle_file_upload(message: Message, bot: Bot) -> None:
    user = message.from_user
    logger.info("Upload from user %s (%s)", user.id, user.username)

    # Admin-only upload restriction
    if not is_admin(user.id):
        await message.answer("⛔ <b>Uploads are restricted to admins only.</b>", parse_mode="HTML")
        return

    db = get_db()
    file_repo = FileRepository(db)

    # ── Extract metadata ──────────────────────────────────────────────────────
    filename, file_id, file_unique_id, file_size, mime_type = extract_file_info(message)
    file_type = detect_file_type(message)

    # ── Feature 1: Duplicate detection ───────────────────────────────────────
    duplicate = await file_repo.find_duplicate(user.id, file_unique_id)
    if duplicate:
        await message.answer(
            f"⚠️ <b>Duplicate detected!</b>\n\n"
            f"You already stored this file:\n"
            f"📄 <b>{duplicate.effective_name}</b>\n"
            f"🔑 ID: <code>{duplicate.id}</code>\n"
            f"📅 Uploaded: {duplicate.upload_date.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Use /get <code>{duplicate.id}</code> to retrieve it.",
            parse_mode="HTML",
        )
        return

    # ── Copy to internal channel ──────────────────────────────────────────────
    processing_msg = await message.answer("⏳ Storing your file...")

    try:
        copied = await bot.copy_message(
            chat_id=settings.storage_channel_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            caption=(
                f"[STORED]\nUser: {user.id} (@{user.username or 'N/A'})\n"
                f"File: {filename}\nType: {file_type}\n"
                f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            ),
        )
    except Exception as exc:
        logger.exception("Channel copy failed: %s", exc)
        await processing_msg.edit_text(
            f"❌ Storage failed: <code>{type(exc).__name__}</code>", parse_mode="HTML"
        )
        return

    # ── Build record (optionally with auto-expiry) ────────────────────────────
    expires_at = None
    if settings.default_expiry_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.default_expiry_days)

    record = FileRecord(
        user_id=user.id,
        username=user.username,
        original_filename=filename,
        file_type=file_type,
        mime_type=mime_type,
        file_size=file_size,
        internal_message_id=copied.message_id,
        channel_id=settings.storage_channel_id,
        telegram_file_id=file_id,
        telegram_file_unique_id=file_unique_id,
        caption=message.caption,
        expires_at=expires_at,
    )

    # ── Save to MongoDB ───────────────────────────────────────────────────────
    try:
        record_id = await file_repo.insert(record)
    except Exception as exc:
        logger.exception("MongoDB insert failed: %s", exc)
        logger.error(
            "ORPHANED FILE — channel=%s msg=%s", settings.storage_channel_id, copied.message_id
        )
        await processing_msg.edit_text(
            f"❌ Metadata save failed: <code>{type(exc).__name__}</code>", parse_mode="HTML"
        )
        return

    # ── Confirm to user with action keyboard ──────────────────────────────────
    expiry_note = (
        f"\n⏰ <b>Expires:</b> {expires_at.strftime('%Y-%m-%d')}" if expires_at else ""
    )
    await processing_msg.edit_text(
        f"✅ <b>File stored!</b>\n\n"
        f"📄 <b>Name:</b> {filename}\n"
        f"📦 <b>Type:</b> {file_type}\n"
        f"📏 <b>Size:</b> {format_size(file_size)}"
        f"{expiry_note}\n\n"
        f"🔑 <b>File ID:</b>\n<code>{record_id}</code>",
        parse_mode="HTML",
        reply_markup=build_file_action_keyboard(record_id),
    )
    logger.info("Stored: user=%s record=%s msg=%s", user.id, record_id, copied.message_id)
