"""Handler для основного диалога с лидами."""

from datetime import datetime

from aiogram import F, Router
from aiogram.types import Message

from src.database.models import Conversation, Lead, MessageRole
from src.services.llm import generate_response
from src.services.notifier import notify_owner_about_lead
from src.types import LLMResponse
from src.utils.logger import logger

router = Router(name="conversation")


@router.message(F.text)
async def handle_message(message: Message) -> None:
    """
    Обработка всех текстовых сообщений от лидов.
    Основной диалог с квалификацией.
    """
    if not message.from_user or not message.text:
        return

    telegram_id: int = message.from_user.id
    user_message: str = message.text

    # Получаем лида из БД
    lead = await Lead.get_or_none(telegram_id=telegram_id)

    if not lead:
        # AICODE-NOTE: Если лида нет в БД, значит он не прошёл /start.
        # Создаём его здесь для удобства (хотя лучше направить на /start).
        lead = await Lead.create(
            telegram_id=telegram_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            last_message_at=datetime.utcnow(),
        )
        logger.info(f"Создан новый лид без /start: {lead}")

    # Обновляем время последнего сообщения
    lead.last_message_at = datetime.utcnow()
    await lead.save()

    # Сохраняем сообщение лида в историю
    await Conversation.create(
        lead=lead,
        role=MessageRole.USER,
        content=user_message,
    )

    logger.info(f"Сообщение от лида {lead}: {user_message[:50]}")

    # Генерируем ответ через LLM
    try:
        response_data: LLMResponse = await generate_response(lead, user_message)

        bot_response: str = response_data["response"]
        new_status = response_data["status"]
        action = response_data["action"]

        # AICODE-TODO: Реализовать обработку action для MVP
        # - action="schedule_meeting" → запросить время встречи у лида (inline keyboard)
        # - action="send_materials" → отправить портфолио/кейсы (настроить ссылки в .env)
        # - action="continue" → просто продолжить диалог (уже работает)
        if action == "schedule_meeting":
            # TODO: Вызвать handler для назначения встречи
            pass
        elif action == "send_materials":
            # TODO: Отправить материалы (ссылки из config)
            pass

        # Для action == "continue" просто продолжаем — отправляем ответ ниже

        # Сохраняем ответ бота в историю
        await Conversation.create(
            lead=lead,
            role=MessageRole.ASSISTANT,
            content=bot_response,
        )

        # Обновляем статус лида (если изменился)
        if new_status and new_status != lead.status:
            old_status = lead.status
            lead.status = new_status
            await lead.save()
            logger.info(f"Статус лида {lead} изменён: {old_status.value} → {new_status.value}")

            # Уведомляем владельца о новом горячем/тёплом лиде
            await notify_owner_about_lead(lead)

        # Отправляем ответ лиду
        await message.answer(bot_response)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения от {lead}: {e}", exc_info=True)

        # AICODE-TODO: Добавить более умную обработку ошибок (retry, fallback ответы)
        await message.answer(
            "Извините, произошла ошибка. Попробуйте переформулировать вопрос или напишите позже."
        )
