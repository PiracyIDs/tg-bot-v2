"""
Download / retrieval handlers:
  /get <id>       — retrieve a file
  /list [page]    — interactive inline keyboard browser
  /search <name>  — search by filename
  /tag <tag>      — search by tag
  /share <code>   — claim a shared file
  /rename <id>    — rename a file
  /delete <id>    — delete a file record
  /mystats        — show quota usage
  /settoken       — set your download verification token
  /verify         — verify token to enable downloads

Callback handlers for the inline keyboards.
"""
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.database.connection import get_db
from bot.database.repositories.file_repo import FileRepository
from bot.database.repositories.quota_repo import QuotaRepository
from bot.utils.file_utils import format_size, parse_tags
from bot.utils.keyboards import (
    build_delete_confirm_keyboard,
    build_expiry_keyboard,
    build_file_action_keyboard,
    build_file_list_keyboard,
)
from bot.utils.states import RenameStates, TagStates, TokenStates

logger = logging.getLogger(__name__)
router = Router(name="download")
PAGE_SIZE = 8


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_user_ids


# ─────────────────────────────────────────────────────────────────────────────
# /get <file_id>
# ─────────────────────────────────────────────────────────────────────────────

async def _deliver_file(
    bot: Bot,
    chat_id: int,
    record_id: str,
    requesting_user_id: int,
) -> str | None:
    """
    Shared delivery helper used by /get and callback 'get:'.
    Returns an error string or None on success.
    """
    repo = FileRepository(get_db())
    record = await repo.get_by_id(record_id)

    if not record:
        return "❌ File not found."
    if record.user_id != requesting_user_id:
        # Check if requester is using a share code elsewhere — not here
        return "❌ You don't have permission to access this file."

    try:
        await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=record.channel_id,
            message_id=record.internal_message_id,
            caption=record.caption,
        )
    except Exception as exc:
        logger.exception("Delivery failed for record %s: %s", record_id, exc)
        return f"❌ Retrieval failed: <code>{type(exc).__name__}</code>"

    return None  # success


@router.message(Command("get"))
async def cmd_get_file(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id

    if not is_admin(user_id):
        quota_repo = QuotaRepository(get_db())
        if not await quota_repo.is_token_verified(user_id):
            stored_token = await quota_repo.get_download_token(user_id)
            if not stored_token:
                await message.answer(
                    "🔐 <b>Token required for downloads.</b>\n\n"
                    "Use /settoken to set your download token first.",
                    parse_mode="HTML",
                )
                return
            await message.answer(
                "🔐 <b>Token verification required.</b>\n\n"
                "Use /verify to verify your token before downloading.",
                parse_mode="HTML",
            )
            return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /get <code>&lt;file_id&gt;</code>", parse_mode="HTML")
        return
    err = await _deliver_file(bot, message.chat.id, args[1].strip(), message.from_user.id)
    if err:
        await message.answer(err, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# /list — Interactive inline keyboard browser
# ─────────────────────────────────────────────────────────────────────────────

async def _send_file_list(target: Message | CallbackQuery, page: int) -> None:
    """Render the paginated file browser. Works for both messages and callbacks."""
    if isinstance(target, CallbackQuery):
        user_id = target.from_user.id
        send = target.message.edit_text
    else:
        user_id = target.from_user.id
        send = target.answer

    repo = FileRepository(get_db())
    total = await repo.count_by_user(user_id)

    if total == 0:
        text = "📂 You have no stored files yet. Send me a file to get started!"
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text)
        else:
            await target.answer(text)
        return

    total_pages = max(1, -(-total // PAGE_SIZE))
    page = max(1, min(page, total_pages))
    records = await repo.list_by_user(user_id, page=page, page_size=PAGE_SIZE)

    await send(
        f"📁 <b>Your Files</b> — Page {page}/{total_pages} ({total} total)\n"
        "Tap a file to download it:",
        parse_mode="HTML",
        reply_markup=build_file_list_keyboard(records, page, total_pages),
    )


@router.message(Command("list"))
async def cmd_list_files(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    try:
        page = int(args[1]) if len(args) > 1 else 1
    except ValueError:
        page = 1
    await _send_file_list(message, page)


@router.callback_query(F.data.startswith("page:"))
async def cb_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])
    await _send_file_list(callback, page)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()  # Page indicator button — do nothing


# ─────────────────────────────────────────────────────────────────────────────
# Inline "get" from the browser list
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("get:"))
async def cb_get_file(callback: CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id

    if not is_admin(user_id):
        quota_repo = QuotaRepository(get_db())
        if not await quota_repo.is_token_verified(user_id):
            stored_token = await quota_repo.get_download_token(user_id)
            if not stored_token:
                await callback.answer("🔐 Set a token with /settoken first.", show_alert=True)
                return
            await callback.answer("🔐 Verify your token with /verify first.", show_alert=True)
            return

    record_id = callback.data.split(":", 1)[1]
    await callback.answer("📥 Sending…")
    err = await _deliver_file(bot, callback.message.chat.id, record_id, user_id)
    if err:
        await callback.message.answer(err, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# /search <query>
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("Usage: /search <code>&lt;query&gt;</code>", parse_mode="HTML")
        return

    query = args[1].strip()
    repo = FileRepository(get_db())
    records = await repo.search_by_filename(message.from_user.id, query)

    if not records:
        await message.answer(f"🔍 No files matching <code>{query}</code>.", parse_mode="HTML")
        return

    lines = [f"🔍 <b>Results for:</b> <code>{query}</code>\n"]
    for rec in records:
        lines.append(
            f"• <code>{rec.id}</code> — <b>{rec.effective_name}</b>\n"
            f"  {rec.file_type} · {format_size(rec.file_size)} · "
            f"{rec.upload_date.strftime('%Y-%m-%d')}\n"
            f"  /get <code>{rec.id}</code>\n"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# Feature 2: Tag search — /tag <tagname>
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("tag"))
async def cmd_search_by_tag(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("Usage: /tag <code>&lt;tagname&gt;</code>", parse_mode="HTML")
        return

    tag = args[1].strip().lower().lstrip("#")
    repo = FileRepository(get_db())
    records = await repo.search_by_tag(message.from_user.id, tag)

    if not records:
        await message.answer(f"🏷️ No files tagged <code>#{tag}</code>.", parse_mode="HTML")
        return

    lines = [f"🏷️ <b>Files tagged</b> <code>#{tag}</code>\n"]
    for rec in records:
        lines.append(
            f"• <code>{rec.id}</code> — <b>{rec.effective_name}</b>\n"
            f"  /get <code>{rec.id}</code>\n"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# Feature: File sharing — /share <file_id>  and  /claim <code>
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("share"))
async def cmd_share(message: Message) -> None:
    """Generate a share code for a file (anyone with the code can claim it)."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /share <code>&lt;file_id&gt;</code>", parse_mode="HTML")
        return

    record_id = args[1].strip()
    repo = FileRepository(get_db())
    code = await repo.create_or_get_share_code(record_id, message.from_user.id)

    if not code:
        await message.answer("❌ File not found or access denied.")
        return

    await message.answer(
        f"🔗 <b>Share Code Generated</b>\n\n"
        f"Code: <code>{code}</code>\n\n"
        f"Anyone using this bot can claim the file with:\n"
        f"/claim <code>{code}</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("share:"))
async def cb_share(callback: CallbackQuery) -> None:
    record_id = callback.data.split(":", 1)[1]
    repo = FileRepository(get_db())
    code = await repo.create_or_get_share_code(record_id, callback.from_user.id)

    if not code:
        await callback.answer("❌ Could not generate share code.", show_alert=True)
        return

    await callback.message.answer(
        f"🔗 <b>Share Code:</b> <code>{code}</code>\n\n"
        f"Anyone can claim this file with:\n/claim <code>{code}</code>",
        parse_mode="HTML",
    )
    await callback.answer("Share code sent!")


@router.message(Command("claim"))
async def cmd_claim(message: Message, bot: Bot) -> None:
    """
    Claim a shared file using its share code.
    The bot copies the file from the internal channel to the claimer.
    """
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /claim <code>&lt;share_code&gt;</code>", parse_mode="HTML")
        return

    code = args[1].strip().upper()
    repo = FileRepository(get_db())
    record = await repo.get_by_share_code(code)

    if not record:
        await message.answer("❌ Invalid or expired share code.")
        return

    try:
        await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=record.channel_id,
            message_id=record.internal_message_id,
            caption=record.caption,
        )
        await repo.increment_share_uses(record.id)
        await message.answer(
            f"✅ <b>File received!</b>\n"
            f"📄 {record.effective_name} (shared by @{record.username or 'anonymous'})",
            parse_mode="HTML",
        )
        logger.info("User %s claimed file %s via code %s", message.from_user.id, record.id, code)
    except Exception as exc:
        logger.exception("Claim delivery failed: %s", exc)
        await message.answer(f"❌ Retrieval failed: <code>{type(exc).__name__}</code>", parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# Feature: Rename — FSM flow
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("rename"))
async def cmd_rename(message: Message, state: FSMContext) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /rename <code>&lt;file_id&gt;</code>", parse_mode="HTML")
        return
    await state.set_state(RenameStates.waiting_for_new_name)
    await state.update_data(record_id=args[1].strip())
    await message.answer("✏️ Send me the new display name for this file:")


@router.callback_query(F.data.startswith("rename:"))
async def cb_rename(callback: CallbackQuery, state: FSMContext) -> None:
    record_id = callback.data.split(":", 1)[1]
    await state.set_state(RenameStates.waiting_for_new_name)
    await state.update_data(record_id=record_id)
    await callback.message.answer("✏️ Send me the new display name for this file:")
    await callback.answer()


@router.message(RenameStates.waiting_for_new_name)
async def process_rename(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    record_id = data.get("record_id")
    new_name = message.text.strip()

    if not new_name or len(new_name) > 255:
        await message.answer("❌ Name must be 1–255 characters.")
        return

    repo = FileRepository(get_db())
    success = await repo.rename(record_id, message.from_user.id, new_name)
    await state.clear()

    if success:
        await message.answer(
            f"✅ File renamed to <b>{new_name}</b>", parse_mode="HTML"
        )
    else:
        await message.answer("❌ File not found or access denied.")


# ─────────────────────────────────────────────────────────────────────────────
# Feature: Tagging — FSM flow
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tag:"))
async def cb_tag(callback: CallbackQuery, state: FSMContext) -> None:
    record_id = callback.data.split(":", 1)[1]
    await state.set_state(TagStates.waiting_for_tags)
    await state.update_data(record_id=record_id)
    await callback.message.answer(
        "🏷️ Send me tags for this file.\n"
        "Example: <code>#invoice #2024 #work</code> or just <code>invoice 2024 work</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(TagStates.waiting_for_tags)
async def process_tags(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    record_id = data.get("record_id")
    tags = parse_tags(message.text)

    if not tags:
        await message.answer("❌ No valid tags found. Try: <code>#invoice #2024</code>", parse_mode="HTML")
        return

    repo = FileRepository(get_db())
    success = await repo.set_tags(record_id, message.from_user.id, tags)
    await state.clear()

    if success:
        tag_display = " ".join(f"<code>#{t}</code>" for t in tags)
        await message.answer(f"✅ Tags set: {tag_display}", parse_mode="HTML")
    else:
        await message.answer("❌ File not found or access denied.")


# ─────────────────────────────────────────────────────────────────────────────
# Feature: Set Expiry — inline keyboard selection
# ─────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("expiry:"))
async def cb_expiry_menu(callback: CallbackQuery) -> None:
    record_id = callback.data.split(":", 1)[1]
    await callback.message.answer(
        "⏰ How long should this file be kept?",
        reply_markup=build_expiry_keyboard(record_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_expiry:"))
async def cb_set_expiry(callback: CallbackQuery) -> None:
    _, record_id, days_str = callback.data.split(":")
    days = int(days_str)

    repo = FileRepository(get_db())
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=days) if days > 0 else None
    )
    success = await repo.set_expiry(record_id, callback.from_user.id, expires_at)

    if success:
        msg = (
            f"⏰ File will expire on <b>{expires_at.strftime('%Y-%m-%d')}</b>"
            if expires_at
            else "✅ File expiry removed — it will be kept indefinitely."
        )
        await callback.message.answer(msg, parse_mode="HTML")
    else:
        await callback.message.answer("❌ File not found or access denied.")
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Delete with confirmation
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("delete"))
async def cmd_delete(message: Message) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: /delete <code>&lt;file_id&gt;</code>", parse_mode="HTML")
        return
    record_id = args[1].strip()
    await message.answer(
        f"🗑️ Delete file <code>{record_id}</code>? This cannot be undone.",
        parse_mode="HTML",
        reply_markup=build_delete_confirm_keyboard(record_id),
    )


@router.callback_query(F.data.startswith("delete_confirm:"))
async def cb_delete_confirm(callback: CallbackQuery) -> None:
    record_id = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        f"🗑️ Delete file <code>{record_id}</code>? This cannot be undone.",
        parse_mode="HTML",
        reply_markup=build_delete_confirm_keyboard(record_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_do:"))
async def cb_delete_do(callback: CallbackQuery) -> None:
    record_id = callback.data.split(":", 1)[1]
    db = get_db()
    file_repo = FileRepository(db)
    quota_repo = QuotaRepository(db)

    record = await file_repo.get_by_id(record_id)
    if record and record.user_id == callback.from_user.id:
        deleted = await file_repo.delete_by_id(record_id, callback.from_user.id)
        if deleted:
            await quota_repo.remove_usage(callback.from_user.id, record.file_size or 0)
            await callback.message.edit_text(
                f"🗑️ File <code>{record_id}</code> deleted.", parse_mode="HTML"
            )
        else:
            await callback.message.edit_text("❌ Deletion failed.")
    else:
        await callback.message.edit_text("❌ File not found or access denied.")
    await callback.answer()


@router.callback_query(F.data.startswith("delete_cancel:"))
async def cb_delete_cancel(callback: CallbackQuery) -> None:
    await callback.message.edit_text("✅ Deletion cancelled.")
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# /mystats — quota usage
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("mystats"))
async def cmd_mystats(message: Message) -> None:
    quota_repo = QuotaRepository(get_db())
    quota = await quota_repo.get(message.from_user.id)

    bar_length = 20
    if quota.is_unlimited:
        bar = "∞ unlimited"
        pct_str = "Unlimited"
    else:
        filled = int(quota.usage_percent / 100 * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        pct_str = f"{quota.usage_percent:.1f}%"

    await message.answer(
        f"📊 <b>Your Storage Stats</b>\n\n"
        f"Files stored: <b>{quota.file_count}</b>\n"
        f"Space used:   <b>{format_size(quota.used_bytes)}</b>\n"
        f"Quota:        <b>{'Unlimited' if quota.is_unlimited else format_size(quota.quota_bytes)}</b>\n\n"
        f"[{bar}] {pct_str}",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Token verification for non-admin downloads
# ─────────────────────────────────────────────────────────────────────────────

@router.message(Command("settoken"))
async def cmd_settoken(message: Message, state: FSMContext) -> None:
    """Set your download verification token."""
    if is_admin(message.from_user.id):
        await message.answer("ℹ️ Admins don't need a token — you can download freely.")
        return

    await state.set_state(TokenStates.waiting_for_new_token)
    await message.answer(
        "🔐 <b>Set Download Token</b>\n\n"
        "Send me a token (password) that you'll need to enter before downloading files.\n\n"
        "⚠️ Choose something memorable — you'll need this every time you download.",
        parse_mode="HTML",
    )


@router.message(TokenStates.waiting_for_new_token)
async def process_new_token(message: Message, state: FSMContext) -> None:
    token = message.text.strip()
    if len(token) < 4:
        await message.answer("❌ Token must be at least 4 characters. Try again:")
        return

    quota_repo = QuotaRepository(get_db())
    await quota_repo.set_download_token(message.from_user.id, token)
    await state.clear()
    await message.answer(
        "✅ <b>Token set successfully!</b>\n\n"
        f"Your download token is: <code>{token}</code>\n\n"
        "Use /verify before downloading files.",
        parse_mode="HTML",
    )


@router.message(Command("verify"))
async def cmd_verify(message: Message, state: FSMContext) -> None:
    """Verify your token to enable downloads."""
    if is_admin(message.from_user.id):
        await message.answer("ℹ️ Admins don't need token verification — you can download freely.")
        return

    quota_repo = QuotaRepository(get_db())
    stored_token = await quota_repo.get_download_token(message.from_user.id)

    if not stored_token:
        await message.answer(
            "❌ You haven't set a token yet.\n\nUse /settoken to set one first.",
            parse_mode="HTML",
        )
        return

    await state.set_state(TokenStates.waiting_for_token)
    await state.update_data(stored_token=stored_token)
    await message.answer("🔐 Send your download token to verify:", parse_mode="HTML")


@router.message(TokenStates.waiting_for_token)
async def process_token_verify(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    stored_token = data.get("stored_token")
    user_token = message.text.strip()

    await state.clear()

    if user_token == stored_token:
        from datetime import timedelta
        quota_repo = QuotaRepository(get_db())
        verified_until = datetime.now(timezone.utc) + timedelta(minutes=30)
        await quota_repo.set_token_verified(message.from_user.id, verified_until)
        await message.answer(
            "✅ <b>Token verified!</b>\n\n"
            "You can now download files for 30 minutes.\n"
            "Use /get, /list, or tap files to download.",
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Incorrect token. Try /verify again.")
