"""Сервис квалификации лидов и извлечения информации из диалогов."""

from src.database.models import Conversation, Lead, LeadStatus
from src.utils.logger import logger


async def update_lead_status(lead: Lead, new_status: LeadStatus) -> None:
    """
    Обновляет статус лида в БД.

    Args:
        lead: Объект лида
        new_status: Новый статус (HOT, WARM, COLD, NEW)
    """
    if lead.status == new_status:
        return  # Статус не изменился

    old_status = lead.status
    lead.status = new_status
    await lead.save()

    logger.info(f"Статус лида {lead.id} изменён: {old_status.value} → {new_status.value}")


async def extract_lead_info(lead: Lead) -> dict[str, str | None]:
    """
    Извлекает информацию о лиде из истории диалога через LLM.

    AICODE-TODO: Реализовать для MVP — критично для заполнения полей БД
    Логика:
    1. Загрузить всю историю диалога (Conversation)
    2. Отправить промпт в Claude: "Извлеки задачу, бюджет, срок из диалога"
    3. Парсить JSON ответ
    4. Обновить поля lead.task, lead.budget, lead.deadline
    5. Сохранить в БД

    Args:
        lead: Объект лида из БД

    Returns:
        dict с полями: task, budget, deadline (или None если не найдено)
    """
    # Загружаем историю диалога
    conversation_history = await Conversation.filter(lead=lead).order_by("created_at").all()

    if not conversation_history:
        logger.warning(f"Нет истории диалога для лида {lead.id}")
        return {"task": None, "budget": None, "deadline": None}

    # TODO: Отправить запрос к Claude для извлечения информации
    # Промпт примерно такой:
    # """
    # Проанализируй диалог и извлеки:
    # - task: Какая задача у клиента? (одной фразой)
    # - budget: Бюджет (если упомянут)
    # - deadline: Когда нужно (если упомянут)
    #
    # Верни JSON: {"task": "...", "budget": "...", "deadline": "..."}
    # Если не найдено — null
    # """

    logger.warning(f"extract_lead_info() для лида {lead.id} — НЕ РЕАЛИЗОВАНО (TODO)")

    # Заглушка
    return {"task": None, "budget": None, "deadline": None}


async def qualify_lead_from_conversation(lead: Lead) -> LeadStatus:
    """
    Квалифицирует лида на основе истории диалога.

    AICODE-NOTE: Эта функция пока не используется, т.к. квалификация
    происходит в services/llm.py (generate_response).
    Оставлена для возможного будущего использования (batch processing, re-qualification).

    Args:
        lead: Объект лида

    Returns:
        Оценённый статус (HOT, WARM, COLD, NEW)
    """
    # AICODE-TODO: Реализовать при необходимости batch-квалификации
    # (например, для переквалификации старых лидов после обновления промптов)
    logger.info(f"qualify_lead_from_conversation для {lead.id} — НЕ РЕАЛИЗОВАНО")
    # AICODE-NOTE: Явное приведение типа для MyPy (Tortoise ORM поле возвращает Any)
    current_status: LeadStatus = lead.status
    return current_status
