"""
Common handlers: /start, /help, catch-all.
"""
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="common")

HELP_TEXT = (
    "👋 <b>File Storage Bot</b> — Enhanced Edition\n\n"

    "<b>📤 Upload</b>\n"
    "Just send any file, photo, video, audio, or voice message.\n\n"

    "<b>📥 Retrieve</b>\n"
    "/get <code>&lt;file_id&gt;</code> — Retrieve a file by ID\n"
    "/list — Browse your files (interactive)\n"
    "/search <code>&lt;query&gt;</code> — Search by filename\n\n"

    "<b>🏷️ Organisation</b>\n"
    "/tag <code>&lt;tagname&gt;</code> — Find files by tag\n"
    "/rename <code>&lt;file_id&gt;</code> — Rename a file\n\n"

    "<b>🔗 Sharing</b>\n"
    "/share <code>&lt;file_id&gt;</code> — Generate a share code\n"
    "/claim <code>&lt;code&gt;</code> — Claim a file shared by someone\n\n"

    "<b>📊 Account</b>\n"
    "/mystats — View your storage quota usage\n"
    "/delete <code>&lt;file_id&gt;</code> — Delete a file\n\n"

    "<b>💡 Tips</b>\n"
    "• After uploading, use the action buttons to tag, rename, share, or set expiry.\n"
    "• Duplicate files are detected automatically.\n"
    "• Files can be set to auto-expire after 1, 7, or 30 days."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message()
async def unhandled(message: Message) -> None:
    await message.answer(
        "❓ Send me a file to store it, or use /help to see all commands."
    )
