"""
Inline keyboard builders for the interactive file browser and confirmations.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.models.file_record import FileRecord
from bot.utils.file_utils import format_size


# ── File list browser ─────────────────────────────────────────────────────────

def build_file_list_keyboard(
    records: list[FileRecord],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """
    Inline keyboard for paginated file browser.
    Each file gets its own row with a ▶️ Get button.
    Bottom row: prev / page indicator / next.
    """
    builder = InlineKeyboardBuilder()

    for rec in records:
        label = f"{rec.effective_name[:28]} ({rec.file_type}, {format_size(rec.file_size)})"
        builder.row(
            InlineKeyboardButton(
                text=f"📥 {label}",
                callback_data=f"get:{rec.id}",
            )
        )

    # Pagination controls
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"page:{page - 1}"))
    nav.append(
        InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop")
    )
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"page:{page + 1}"))

    builder.row(*nav)
    return builder.as_markup()


# ── File detail action keyboard ───────────────────────────────────────────────

def build_file_action_keyboard(record_id: str) -> InlineKeyboardMarkup:
    """Actions shown after a file is stored or retrieved."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔗 Share", callback_data=f"share:{record_id}"),
        InlineKeyboardButton(text="🏷️ Tag", callback_data=f"tag:{record_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Rename", callback_data=f"rename:{record_id}"),
        InlineKeyboardButton(text="⏰ Set Expiry", callback_data=f"expiry:{record_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_confirm:{record_id}"),
    )
    return builder.as_markup()


def build_delete_confirm_keyboard(record_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Yes, delete", callback_data=f"delete_do:{record_id}"),
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"delete_cancel:{record_id}"),
    )
    return builder.as_markup()


def build_expiry_keyboard(record_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    options = [("1 day", 1), ("7 days", 7), ("30 days", 30), ("Never", 0)]
    for label, days in options:
        builder.button(text=label, callback_data=f"set_expiry:{record_id}:{days}")
    builder.adjust(2)
    return builder.as_markup()
