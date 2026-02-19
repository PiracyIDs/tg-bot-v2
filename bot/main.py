"""
Bot entry point — Enhanced Edition.
Wires together aiogram, MongoDB, FSM storage, background tasks,
middleware, and all routers.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.database.connection import connect_to_mongo, close_mongo
from bot.handlers import admin, common, download, upload
from bot.middlewares.auth import AllowlistMiddleware
from bot.tasks.expiry_task import expiry_warning_task


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


async def on_startup(bot: Bot) -> None:
    await connect_to_mongo()
    try:
        chat = await bot.get_chat(settings.storage_channel_id)
        logging.getLogger(__name__).info(
            "Storage channel OK: '%s' (id=%s)", chat.title, chat.id
        )
    except Exception as exc:
        logging.getLogger(__name__).critical(
            "Cannot access storage channel %s: %s", settings.storage_channel_id, exc
        )
        raise SystemExit(1)


async def on_shutdown(bot: Bot) -> None:
    await close_mongo()
    logging.getLogger(__name__).info("Shutdown complete.")


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Telegram File Storage Bot — Enhanced Edition")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # MemoryStorage for FSM (swap for RedisStorage in production clusters)
    dp = Dispatcher(storage=MemoryStorage())

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Middleware
    dp.update.outer_middleware(AllowlistMiddleware())

    # Routers — order matters (most specific first)
    dp.include_router(admin.router)
    dp.include_router(download.router)
    dp.include_router(upload.router)
    dp.include_router(common.router)  # catch-all last

    # Background tasks
    loop = asyncio.get_event_loop()
    expiry_task = loop.create_task(expiry_warning_task(bot))

    logger.info("Polling for updates…")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
    finally:
        expiry_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
