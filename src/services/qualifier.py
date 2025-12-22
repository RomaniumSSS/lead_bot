"""Сервис квалификации лидов и извлечения информации из диалогов."""

import json

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from src.config import settings
from src.database.models import Conversation, Lead, LeadStatus
from src.utils.logger import logger

# Инициализация Claude API клиента
client = AsyncAnthropic(api_key=settings.anthropic_api_key)
MODEL = "claude-sonnet-4-20250514"  # Claude Sonnet 4.5


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

    Анализирует всю историю диалога и автоматически заполняет поля:
    - task (задача клиента)
    - budget (бюджет, если упомянут)
    - deadline (срок выполнения, если упомянут)

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

    # Формируем текст диалога для анализа
    dialog_text = ""
    for conv in conversation_history:
        role = "Клиент" if conv.role.value == "user" else "Бот"
        dialog_text += f"{role}: {conv.content}\n"

    # Промпт для извлечения информации
    extraction_prompt = f"""Проанализируй диалог между ботом и потенциальным клиентом.

Диалог:
{dialog_text}

Извлеки следующую информацию:
1. **task** — Какая конкретная задача у клиента? (одной короткой фразой, максимум 100 символов)
2. **budget** — Бюджет клиента (если упомянут, иначе null)
3. **deadline** — Когда нужно выполнить (если упомянут, иначе null)

**Важно:**
- Если информация не упоминалась в диалоге — верни null
- task должна быть краткой и конкретной
- budget и deadline сохраняй так, как сказал клиент

Верни ТОЛЬКО JSON в формате:
{{
    "task": "краткое описание задачи" или null,
    "budget": "бюджет клиента" или null,
    "deadline": "срок выполнения" или null
}}"""

    try:
        # Запрос к Claude API
        response = await client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": extraction_prompt}],
        )

        # AICODE-NOTE: Извлекаем текст из первого блока ответа
        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            logger.error(f"Claude вернул неожиданный тип блока: {type(first_block)}")
            return {"task": None, "budget": None, "deadline": None}

        response_text: str = first_block.text.strip()

        # AICODE-NOTE: Очищаем от markdown обёртки (```json ... ```)
        cleaned_text = response_text
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        elif cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()

        # Парсим JSON
        extracted_data: dict[str, str | None] = json.loads(cleaned_text)

        # Обновляем поля лида в БД
        if extracted_data.get("task") and not lead.task:
            lead.task = extracted_data["task"]
        if extracted_data.get("budget") and not lead.budget:
            lead.budget = extracted_data["budget"]
        if extracted_data.get("deadline") and not lead.deadline:
            lead.deadline = extracted_data["deadline"]

        await lead.save()

        logger.info(
            f"Извлечена информация для лида {lead.id}: "
            f"task={extracted_data.get('task')}, "
            f"budget={extracted_data.get('budget')}, "
            f"deadline={extracted_data.get('deadline')}"
        )

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON от Claude для лида {lead.id}: {e}")
        logger.debug(f"Response text: {response_text}")
        return {"task": None, "budget": None, "deadline": None}

    except Exception as e:
        logger.error(f"Ошибка при извлечении информации для лида {lead.id}: {e}", exc_info=True)

    else:
        return extracted_data

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
