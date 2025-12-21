"""Главный модуль запуска Telegram-бота."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from tortoise import Tortoise

from src.config import settings
from src.database.config import TORTOISE_ORM
from src.handlers import register_all_handlers
from src.middlewares.logging import LoggingMiddleware
from src.utils.logger import logger


async def on_startup() -> None:
    """Действия при запуске бота."""
    logger.info("🚀 Запуск AI Sales Assistant...")
    logger.info(f"📋 Бизнес: {settings.business_name}")
    logger.info(f"⚙️  Режим: {settings.mode}")

    # Инициализация БД
    await Tortoise.init(config=TORTOISE_ORM)
    logger.info("✅ База данных подключена")

    # AICODE-NOTE: Генерация схемы БД автоматически (только для разработки!)
    # В продакшене используйте миграции через Aerich.
    if settings.mode == "development":
        await Tortoise.generate_schemas()
        logger.info("✅ Схемы БД сгенерированы (dev mode)")


async def on_shutdown() -> None:
    """Действия при остановке бота."""
    logger.info("🛑 Остановка AI Sales Assistant...")

    # Закрываем соединения с БД
    await Tortoise.close_connections()
    logger.info("✅ База данных отключена")


async def main() -> None:
    """Главная функция запуска бота."""

    # Инициализация бота и диспетчера
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )

    dp = Dispatcher()

    # Регистрация middleware
    dp.message.middleware(LoggingMiddleware())

    # Регистрация handlers
    register_all_handlers(dp)

    try:
        # Startup
        await on_startup()

        # Запуск polling
        logger.info("✅ Бот запущен! Ожидание сообщений...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except KeyboardInterrupt:
        logger.info("⏸️  Прервано пользователем (Ctrl+C)")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)

    finally:
        # Shutdown
        await on_shutdown()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
