"""Главный модуль запуска Telegram-бота."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from tortoise import Tortoise

from src.config import settings
from src.database.config import TORTOISE_ORM
from src.handlers import register_all_handlers
from src.middlewares.logging import LoggingMiddleware
from src.services.scheduler import run_scheduler
from src.utils.logger import logger
from src.webhook import remove_webhook, setup_webhook


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

    # Redis storage для персистентности FSM state между рестартами
    redis = Redis.from_url(settings.redis_url)
    storage = RedisStorage(redis=redis)
    dp = Dispatcher(storage=storage)

    # Регистрация middleware
    dp.message.middleware(LoggingMiddleware())

    # Регистрация handlers
    register_all_handlers(dp)

    # Запуск scheduler в фоне
    scheduler_task: asyncio.Task[None] | None = None
    webhook_runner = None

    try:
        # Startup
        await on_startup()

        # Запуск scheduler в фоне
        scheduler_task = asyncio.create_task(run_scheduler(bot))
        logger.info("✅ Планировщик follow-up запущен в фоне")

        # Определяем режим работы бота
        if settings.bot_mode == "webhook":
            # Webhook режим
            if not settings.webhook_url:
                raise ValueError("WEBHOOK_URL не установлен в .env для режима webhook")

            logger.info("🔗 Режим работы: WEBHOOK")
            webhook_runner = await setup_webhook(
                bot=bot,
                dp=dp,
                webhook_url=settings.webhook_url,
                webhook_path=settings.webhook_path,
                port=settings.webhook_port,
            )
            logger.info("✅ Бот запущен в режиме webhook! Ожидание обновлений...")

            # В webhook режиме бот просто ждёт (сервер уже запущен)
            # Ждём бесконечно, пока не будет прервано
            await asyncio.Event().wait()

        else:
            # Polling режим (по умолчанию)
            logger.info("🔄 Режим работы: POLLING")
            logger.info("✅ Бот запущен! Ожидание сообщений...")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except KeyboardInterrupt:
        logger.info("⏸️  Прервано пользователем (Ctrl+C)")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)

    finally:
        # Graceful shutdown scheduler
        if scheduler_task and not scheduler_task.done():
            logger.info("⏹️  Останавливаем планировщик...")
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                logger.info("✅ Планировщик остановлен")

        # Graceful shutdown webhook
        if webhook_runner:
            logger.info("⏹️  Останавливаем webhook сервер...")
            await remove_webhook(bot)
            await webhook_runner.cleanup()
            logger.info("✅ Webhook сервер остановлен")

        # Shutdown
        await on_shutdown()
        await bot.session.close()

        # Закрываем Redis соединение
        await redis.aclose()
        logger.info("✅ Redis соединение закрыто")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
