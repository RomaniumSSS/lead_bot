"""Handler для команд /start, /help и /restart."""

from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.config import settings
from src.database.models import Lead, LeadStatus
from src.handlers.states import ConversationState
from src.keyboards import get_progress_indicator, get_task_keyboard
from src.utils.logger import logger

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    Обработка команды /start.
    Создаёт или получает лида из БД, отправляет приветствие с кнопками.
    """
    if not message.from_user:
        return

    telegram_id: int = message.from_user.id
    username: str | None = message.from_user.username
    first_name: str | None = message.from_user.first_name
    last_name: str | None = message.from_user.last_name

    # Очищаем предыдущий state (если был)
    await state.clear()

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
        # Сбрасываем статус для повторной квалификации (если restart)
        lead.status = LeadStatus.NEW
        lead.task = None
        lead.budget = None
        lead.deadline = None
        await lead.save()

    logger.info(f"{'Новый' if created else 'Существующий'} лид: {lead}")

    # Получаем индикатор прогресса
    progress = get_progress_indicator("TASK")

    # Приветственное сообщение с кнопками
    greeting = (
        f"Привет, {first_name or 'друг'}! 👋\n\n"
        f"Я AI-ассистент **{settings.business_name}**.\n\n"
        f"{settings.business_description}\n\n"
        f"─────────────────\n"
        f"{progress}\n"
        f"─────────────────\n\n"
        f"Расскажите, какая задача у вас есть?"
    )

    await message.answer(greeting, reply_markup=get_task_keyboard())

    # Устанавливаем state для ожидания выбора задачи
    await state.set_state(ConversationState.TASK)

    logger.info(f"Лид {lead.id} перешёл в state TASK")


@router.message(Command("restart"))
async def cmd_restart(message: Message, state: FSMContext) -> None:
    """
    Команда /restart — перезапуск диалога с начала.
    Сбрасывает FSM state и данные квалификации.
    """
    if not message.from_user:
        return

    # Очищаем state
    await state.clear()

    logger.info(f"Лид telegram_id={message.from_user.id} перезапустил диалог")

    # Запускаем диалог заново
    await cmd_start(message, state)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Обработка команды /help."""
    help_text = (
        "🤖 **Как я могу помочь:**\n\n"
        "• Просто напишите мне вашу задачу или вопрос\n"
        "• Я помогу вам сориентироваться и подберу решение\n"
        "• При необходимости назначу встречу с владельцем\n\n"
        "**Команды:**\n"
        "/start — начать диалог\n"
        "/restart — начать заново\n"
        "/help — эта справка\n\n"
        "💬 Я работаю 24/7 и всегда на связи!"
    )

    await message.answer(help_text)
