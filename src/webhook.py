"""Webhook setup для продакшена."""

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web  # type: ignore[import-not-found]

from src.utils.logger import logger


async def setup_webhook(
    bot: Bot,
    dp: Dispatcher,
    webhook_url: str,
    webhook_path: str,
    port: int,
) -> web.AppRunner:
    """
    Настраивает webhook для приёма обновлений от Telegram.

    Args:
        bot: Aiogram Bot instance
        dp: Aiogram Dispatcher instance
        webhook_url: Полный URL webhook (https://domain.com/webhook)
        webhook_path: Путь webhook (/webhook)
        port: Порт для веб-сервера

    Returns:
        web.AppRunner для graceful shutdown
    """
    logger.info(f"🔗 Настройка webhook: {webhook_url}")

    # Установить webhook URL в Telegram
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )
    logger.info("✅ Webhook URL установлен в Telegram")

    # Настроить aiohttp приложение
    app = web.Application()

    # Регистрируем handler для webhook
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=webhook_path)
    setup_application(app, dp, bot=bot)

    # Запустить веб-сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"✅ Webhook сервер запущен на порту {port}")
    logger.info(f"📡 Принимаем обновления на {webhook_path}")

    return runner


async def remove_webhook(bot: Bot) -> None:
    """
    Удаляет webhook и возвращает бота в режим polling.

    Args:
        bot: Aiogram Bot instance
    """
    logger.info("🔗 Удаление webhook...")
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook удалён")
