"""Telegram handlers - обработчики команд и сообщений."""

from aiogram import Router

from src.handlers import admin, conversation, meetings, start
from src.handlers.states import ConversationState


def register_all_handlers(router: Router) -> None:
    """
    Регистрирует все handlers в главный роутер.

    Args:
        router: Главный роутер aiogram
    """
    router.include_router(start.router)
    router.include_router(admin.router)
    router.include_router(meetings.router)
    # Последний, чтобы обрабатывал все остальные сообщения
    router.include_router(conversation.router)


__all__ = ["ConversationState", "register_all_handlers"]
