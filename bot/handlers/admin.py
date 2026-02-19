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
        # Silently ignore non-admins
        return

    db = get_db()
    file_repo = FileRepository(db)
    quota_repo = QuotaRepository(db)

    total_files = await file_repo.total_file_count()
    total_bytes = await file_repo.total_storage_bytes()
    user_count = await file_repo.distinct_user_count()
    all_quotas = await quota_repo.all_quotas()

    # Top 5 users by usage
    top_users = sorted(all_quotas, key=lambda q: q.used_bytes, reverse=True)[:5]
    top_lines = []
    for i, q in enumerate(top_users, 1):
        top_lines.append(
            f"  {i}. User <code>{q.user_id}</code> — "
            f"{format_size(q.used_bytes)} / "
            f"{'∞' if q.is_unlimited else format_size(q.quota_bytes)} "
            f"({q.file_count} files)"
        )

    await message.answer(
        f"🔧 <b>Admin Dashboard</b>\n\n"
        f"👥 Users: <b>{user_count}</b>\n"
        f"📁 Total files: <b>{total_files}</b>\n"
        f"💾 Total storage used: <b>{format_size(total_bytes)}</b>\n\n"
        f"<b>Top users by storage:</b>\n"
        + ("\n".join(top_lines) if top_lines else "  (none)") +
        f"\n\n<b>Admin commands:</b>\n"
        f"/setquota <code>&lt;user_id&gt; &lt;mb&gt;</code> — set user quota\n"
        f"/delfile <code>&lt;record_id&gt;</code> — force-delete any file\n"
        f"/userinfo <code>&lt;user_id&gt;</code> — view user stats",
        parse_mode="HTML",
    )


@router.message(Command("setquota"))
async def cmd_setquota(message: Message) -> None:
    """Admin: /setquota <user_id> <mb>  (0 = unlimited)"""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Usage: /setquota <code>&lt;user_id&gt; &lt;mb&gt;</code>", parse_mode="HTML")
        return

    try:
        target_user = int(parts[1])
        quota_mb = int(parts[2])
    except ValueError:
        await message.answer("❌ user_id and mb must be integers.")
        return

    repo = QuotaRepository(get_db())
    await repo.set_quota(target_user, quota_mb)
    label = "Unlimited" if quota_mb == 0 else f"{quota_mb} MB"
    await message.answer(
        f"✅ Quota for user <code>{target_user}</code> set to <b>{label}</b>.",
        parse_mode="HTML",
    )
    logger.info("Admin %s set quota for user %s to %s MB", message.from_user.id, target_user, quota_mb)


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
    quota_repo = QuotaRepository(db)

    record = await file_repo.get_by_id(record_id)
    if not record:
        await message.answer("❌ Record not found.")
        return

    # Delete bypassing ownership
    from bson import ObjectId
    result = await file_repo.col.delete_one({"_id": ObjectId(record_id)})
    if result.deleted_count:
        await quota_repo.remove_usage(record.user_id, record.file_size or 0)
        await message.answer(
            f"✅ Deleted record <code>{record_id}</code> (owner: {record.user_id}).",
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Deletion failed.")


@router.message(Command("userinfo"))
async def cmd_userinfo(message: Message) -> None:
    """Admin: show a specific user's quota and recent files."""
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

    lines = [
        f"👤 <b>User</b> <code>{target_user}</code>\n",
        f"Files: <b>{quota.file_count}</b>",
        f"Used:  <b>{format_size(quota.used_bytes)}</b>",
        f"Quota: <b>{'Unlimited' if quota.is_unlimited else format_size(quota.quota_bytes)}</b>\n",
        "<b>Recent files:</b>",
    ]
    for r in recent:
        lines.append(f"  • <code>{r.id}</code> — {r.effective_name} ({format_size(r.file_size)})")

    await message.answer("\n".join(lines), parse_mode="HTML")
