"""Middleware для логирования всех входящих сообщений."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.utils.logger import logger


class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования всех входящих сообщений."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """
        Логирует входящее сообщение и передаёт его дальше.

        Args:
            handler: Следующий обработчик в цепочке
            event: Входящее событие (TelegramObject)
            data: Дополнительные данные

        Returns:
            Результат выполнения handler
        """
        # Логируем только если это Message
        if isinstance(event, Message):
            user = event.from_user
            user_id = user.id if user else "Unknown"
            username = user.username if user else "Unknown"
            text = event.text or "<non-text message>"

            logger.info(f"📨 Message from {username} (ID: {user_id}): {text[:100]}")

        # Передаём управление следующему обработчику
        return await handler(event, data)
