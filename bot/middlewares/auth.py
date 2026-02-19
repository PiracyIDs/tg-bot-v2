"""
Allowlist middleware: gates updates by user_id.
Empty ALLOWED_USER_IDS = open access.
"""
import logging
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from bot.config import settings

logger = logging.getLogger(__name__)


class AllowlistMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not settings.allowed_user_ids:
            return await handler(event, data)

        update: Update = data.get("event_update")
        user = None
        if update:
            if update.message:
                user = update.message.from_user
            elif update.callback_query:
                user = update.callback_query.from_user

        if user and user.id not in settings.allowed_user_ids:
            logger.warning("Blocked unauthorized user %s", user.id)
            return  # Silently drop

        return await handler(event, data)
