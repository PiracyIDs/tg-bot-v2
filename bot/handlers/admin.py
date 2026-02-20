"""
Admin panel — /admin command.
Only accessible to users listed in ADMIN_USER_IDS.
"""
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.database.connection import get_db
from bot.database.repositories.file_repo import FileRepository
from bot.database.repositories.quota_repo import QuotaRepository
from bot.utils.file_utils import format_size

logger = logging.getLogger(__name__)
router = Router(name="admin")


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_user_ids


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    db = get_db()
    file_repo = FileRepository(db)
    quota_repo = QuotaRepository(db)

    total_files = await file_repo.total_file_count()
    total_bytes = await file_repo.total_storage_bytes()
    user_count = await file_repo.distinct_user_count()
    all_quotas = await quota_repo.all_quotas()

    top_users = sorted(all_quotas, key=lambda q: q.bandwidth_used, reverse=True)[:5]
    top_lines = []
    for i, q in enumerate(top_users, 1):
        bw_str = f"{format_size(q.bandwidth_used)} / {'∞' if q.is_unlimited else format_size(q.bandwidth_limit)}"
        dl_str = f"{q.download_count} dl" + (f" / {q.download_limit}" if q.download_limit > 0 else "")
        top_lines.append(f"  {i}. User <code>{q.user_id}</code> — {bw_str} ({dl_str})")

    await message.answer(
        f"🔧 <b>Admin Dashboard</b>\n\n"
        f"👥 Users: <b>{user_count}</b>\n"
        f"📁 Total files: <b>{total_files}</b>\n"
        f"💾 Total storage used: <b>{format_size(total_bytes)}</b>\n\n"
        f"<b>Top users by download bandwidth:</b>\n"
        + ("\n".join(top_lines) if top_lines else "  (none)") +
        f"\n\n<b>Admin commands:</b>\n"
        f"/setquota <code>&lt;user_id&gt; &lt;bandwidth_mb&gt; [dl_limit]</code> — set download quota\n"
        f"/delfile <code>&lt;record_id&gt;</code> — force-delete any file\n"
        f"/userinfo <code>&lt;user_id&gt;</code> — view user stats",
        parse_mode="HTML",
    )


@router.message(Command("setquota"))
async def cmd_setquota(message: Message) -> None:
    """Admin: /setquota <user_id> <bandwidth_mb> [download_limit] (0 = unlimited)"""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(
            "Usage: /setquota <code>&lt;user_id&gt; &lt;bandwidth_mb&gt; [download_limit]</code>\n"
            "Example: /setquota <code>12345678 500 50</code> — 500MB bandwidth, 50 downloads/day",
            parse_mode="HTML"
        )
        return

    try:
        target_user = int(parts[1])
        bandwidth_mb = int(parts[2])
        download_limit = int(parts[3]) if len(parts) > 3 else 0
    except ValueError:
        await message.answer("❌ user_id, bandwidth_mb, and download_limit must be integers.")
        return

    repo = QuotaRepository(get_db())
    await repo.set_quota(target_user, bandwidth_mb, download_limit)
    bw_label = "Unlimited" if bandwidth_mb == 0 else f"{bandwidth_mb} MB/day"
    dl_label = "Unlimited" if download_limit == 0 else f"{download_limit}/day"
    await message.answer(
        f"✅ Download quota for user <code>{target_user}</code> set to:\n"
        f"📦 Bandwidth: <b>{bw_label}</b>\n"
        f"📊 Downloads: <b>{dl_label}</b>",
        parse_mode="HTML",
    )
    logger.info("Admin %s set quota for user %s to %s MB, %s downloads", 
                message.from_user.id, target_user, bandwidth_mb, download_limit)


@router.message(Command("delfile"))
async def cmd_admin_delete(message: Message) -> None:
    """Admin: force-delete any file record by ID (bypasses ownership check)."""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /delfile <code>&lt;record_id&gt;</code>", parse_mode="HTML")
        return

    record_id = parts[1].strip()
    db = get_db()
    file_repo = FileRepository(db)

    record = await file_repo.get_by_id(record_id)
    if not record:
        await message.answer("❌ Record not found.")
        return

    from bson import ObjectId
    result = await file_repo.col.delete_one({"_id": ObjectId(record_id)})
    if result.deleted_count:
        await message.answer(
            f"✅ Deleted record <code>{record_id}</code> (owner: {record.user_id}).",
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Deletion failed.")


@router.message(Command("userinfo"))
async def cmd_userinfo(message: Message) -> None:
    """Admin: show a specific user's download quota and recent files."""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /userinfo <code>&lt;user_id&gt;</code>", parse_mode="HTML")
        return

    try:
        target_user = int(parts[1].strip())
    except ValueError:
        await message.answer("❌ user_id must be an integer.")
        return

    db = get_db()
    file_repo = FileRepository(db)
    quota_repo = QuotaRepository(db)

    quota = await quota_repo.get(target_user)
    recent = await file_repo.list_by_user(target_user, page=1, page_size=5)

    bw_label = "Unlimited" if quota.is_unlimited else format_size(quota.bandwidth_limit)
    dl_label = "Unlimited" if quota.download_limit == 0 else str(quota.download_limit)
    reset_str = quota.quota_reset_time.strftime('%Y-%m-%d %H:%M') if quota.quota_reset_time else "Not set"

    lines = [
        f"👤 <b>User</b> <code>{target_user}</code>\n",
        f"📥 <b>Download Stats:</b>",
        f"  Bandwidth: {format_size(quota.bandwidth_used)} / {bw_label}",
        f"  Downloads: {quota.download_count}" + (f" / {quota.download_limit}" if quota.download_limit > 0 else ""),
        f"  Reset at: {reset_str}\n",
        "<b>Recent files:</b>",
    ]
    for r in recent:
        lines.append(f"  • <code>{r.id}</code> — {r.effective_name} ({format_size(r.file_size)})")

    await message.answer("\n".join(lines), parse_mode="HTML")
