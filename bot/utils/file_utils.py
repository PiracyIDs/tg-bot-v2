"""
Utility helpers: file type detection, name extraction, size formatting.
"""
from aiogram.types import Message


def detect_file_type(message: Message) -> str:
    if message.document:   return "document"
    if message.photo:      return "photo"
    if message.video:      return "video"
    if message.audio:      return "audio"
    if message.voice:      return "voice"
    if message.video_note: return "video_note"
    if message.sticker:    return "sticker"
    if message.animation:  return "animation"
    return "unknown"


def extract_file_info(
    message: Message,
) -> tuple[str, str, str, int | None, str | None]:
    """
    Returns (filename, file_id, file_unique_id, file_size, mime_type).
    The extra file_unique_id is stable across bots and used for dedup.
    """
    if message.document:
        d = message.document
        return d.file_name or "document", d.file_id, d.file_unique_id, d.file_size, d.mime_type

    if message.photo:
        p = message.photo[-1]
        return (
            f"photo_{p.file_unique_id}.jpg",
            p.file_id, p.file_unique_id,
            p.file_size, "image/jpeg",
        )

    if message.video:
        v = message.video
        return v.file_name or "video.mp4", v.file_id, v.file_unique_id, v.file_size, v.mime_type

    if message.audio:
        a = message.audio
        name = a.file_name or f"{a.performer or 'audio'} - {a.title or 'track'}.mp3"
        return name, a.file_id, a.file_unique_id, a.file_size, a.mime_type

    if message.voice:
        vo = message.voice
        return (
            f"voice_{vo.file_unique_id}.ogg",
            vo.file_id, vo.file_unique_id,
            vo.file_size, "audio/ogg",
        )

    if message.video_note:
        vn = message.video_note
        return (
            f"video_note_{vn.file_unique_id}.mp4",
            vn.file_id, vn.file_unique_id,
            vn.file_size, "video/mp4",
        )

    if message.sticker:
        s = message.sticker
        ext = ".webm" if s.is_video else ".webp"
        return (
            f"sticker_{s.file_unique_id}{ext}",
            s.file_id, s.file_unique_id,
            s.file_size, None,
        )

    if message.animation:
        an = message.animation
        return (
            an.file_name or "animation.gif",
            an.file_id, an.file_unique_id,
            an.file_size, an.mime_type,
        )

    return "unknown_file", "", "", None, None


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "Unknown"
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def parse_tags(text: str) -> list[str]:
    """
    Extract tags from a string.
    Supports: '#invoice #2024' or 'invoice 2024' (space-separated words).
    Returns normalised lowercase list without '#'.
    """
    tokens = text.strip().split()
    return [t.lower().lstrip("#") for t in tokens if t]
