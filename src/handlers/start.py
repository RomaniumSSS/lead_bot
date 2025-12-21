"""Handler для команд /start и /help."""

from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import settings
from src.database.models import Lead, LeadStatus
from src.utils.logger import logger

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """
    Обработка команды /start.
    Создаёт или получает лида из БД и отправляет приветствие.
    """
    if not message.from_user:
        return

    telegram_id: int = message.from_user.id
    username: str | None = message.from_user.username
    first_name: str | None = message.from_user.first_name
    last_name: str | None = message.from_user.last_name

    # Получаем или создаём лида
    lead, created = await Lead.get_or_create(
        telegram_id=telegram_id,
        defaults={
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "status": LeadStatus.NEW,
            "last_message_at": datetime.utcnow(),
        },
    )

    if not created:
        # Обновляем данные существующего лида
        lead.username = username
        lead.first_name = first_name
        lead.last_name = last_name
        lead.last_message_at = datetime.utcnow()
        await lead.save()

    logger.info(f"{'Новый' if created else 'Существующий'} лид: {lead}")

    # Приветственное сообщение
    greeting = (
        f"Привет, {first_name or 'друг'}! 👋\n\n"
        f"Я AI-ассистент **{settings.business_name}**.\n\n"
        f"{settings.business_description}\n\n"
        f"Расскажите, пожалуйста, какая задача у вас есть? "
        f"Чем я могу быть полезен?"
    )

    await message.answer(greeting)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Обработка команды /help."""
    help_text = (
        "🤖 **Как я могу помочь:**\n\n"
        "• Просто напишите мне вашу задачу или вопрос\n"
        "• Я помогу вам сориентироваться и подберу решение\n"
        "• При необходимости назначу встречу с владельцем\n\n"
        "💬 Я работаю 24/7 и всегда на связи!"
    )

    await message.answer(help_text)
