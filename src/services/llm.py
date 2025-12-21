"""Интеграция с Anthropic Claude API для генерации ответов и квалификации лидов."""

import json
from typing import Literal, cast

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, TextBlock

from src.config import settings
from src.database.models import Conversation, Lead, LeadStatus
from src.types import LLMResponse, LLMResponseRaw
from src.utils.logger import logger

# Инициализация Claude API клиента
client = AsyncAnthropic(api_key=settings.anthropic_api_key)


# AICODE-NOTE: Используем Claude 3.5 Sonnet - оптимальное соотношение
# скорости и качества для диалогов
MODEL = "claude-3-5-sonnet-20241022"


async def generate_response(lead: Lead, message: str) -> LLMResponse:
    """
    Генерирует ответ бота и оценивает статус лида через Claude API.

    Args:
        lead: Объект лида из БД
        message: Последнее сообщение от лида

    Returns:
        LLMResponse с полями:
            - response: str - Текст ответа бота
            - status: LeadStatus - Оценка статуса лида
            - action: Literal["continue", "schedule_meeting", "send_materials"]
    """
    # AICODE-TODO: Добавить кэширование системного промпта для экономии токенов

    # Загружаем историю диалога
    conversation_history: list[Conversation] = (
        await Conversation.filter(lead=lead).order_by("created_at").all()
    )

    # Формируем сообщения для Claude
    messages: list[MessageParam] = []
    for conv in conversation_history:
        messages.append({"role": conv.role.value, "content": conv.content})

    # Добавляем текущее сообщение (если ещё не в истории)
    if not messages or messages[-1]["content"] != message:
        messages.append({"role": "user", "content": message})

    # Системный промпт
    system_prompt: str = f"""Ты — AI-ассистент бизнеса "{settings.business_name}".

{settings.business_description}

**Твоя задача:**
1. Вести дружелюбный и профессиональный диалог с потенциальным клиентом.
2. Задавать квалифицирующие вопросы для понимания:
   - Какая задача у клиента?
   - Какой бюджет?
   - Когда нужно решить?
3. Оценивать статус лида:
   - **HOT** (горячий): чёткая задача + бюджет соответствует услугам +
     срочно (на этой неделе, сегодня)
   - **WARM** (тёплый): задача понятна + бюджет средний +
     срок "скоро" (в этом месяце)
   - **COLD** (холодный): задача неясна или бюджет низкий или "пока думаю"
   - **NEW** (новый): недостаточно информации для квалификации

**Tone of Voice:**
- Дружелюбный, но профессиональный
- Помогающий, не навязчивый
- Естественный (как живой человек, а не робот)
- НЕ используй шаблонные фразы типа "Спасибо за обращение"

**Формат ответа:**
Отвечай ТОЛЬКО в JSON формате:
{{
    "response": "Твой ответ клиенту (естественный текст)",
    "status": "HOT|WARM|COLD|NEW",
    "action": "continue|schedule_meeting|send_materials",
    "reasoning": "Краткое объяснение оценки статуса"
}}

**Важно:**
- Если статус HOT — предложи назначить встречу (action: "schedule_meeting")
- Если статус WARM — предложи полезные материалы (action: "send_materials")
- Если статус COLD или NEW — продолжай диалог (action: "continue")
- Задавай вопросы по одному, не спеши
- Если клиент уклоняется от ответа — мягко переспроси или оставь на потом
"""

    try:
        # Запрос к Claude API
        response = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )

        # AICODE-NOTE: Claude возвращает список content blocks, берём первый текстовый
        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            logger.error(f"Claude вернул неожиданный тип блока: {type(first_block)}")
            raise ValueError("Expected TextBlock from Claude response")

        response_text: str = first_block.text

        logger.info(f"Claude response для лида {lead.id}: {response_text[:100]}")

        # Парсим JSON ответ
        try:
            parsed: LLMResponseRaw = json.loads(response_text)
        except json.JSONDecodeError:
            # AICODE-TODO: Иногда Claude возвращает не чистый JSON. Нужен fallback парсинг.
            logger.warning(f"Claude вернул не JSON: {response_text}")
            # Простой fallback
            return {
                "response": response_text,
                "status": LeadStatus.NEW,
                "action": "continue",
            }

        # Конвертируем статус в Enum
        status_str: str = parsed.get("status", "NEW").upper()
        try:
            status: LeadStatus = LeadStatus[status_str]
        except KeyError:
            logger.warning(f"Неизвестный статус от Claude: {status_str}, используем NEW")
            status = LeadStatus.NEW

        # Формируем типизированный ответ
        action_value = parsed.get("action", "continue")
        if action_value not in ["continue", "schedule_meeting", "send_materials"]:
            action_value = "continue"

        # AICODE-NOTE: Используем cast после валидации, чтобы гарантировать корректный тип
        return {
            "response": parsed["response"],
            "status": status,
            "action": cast(Literal["continue", "schedule_meeting", "send_materials"], action_value),
        }

    except Exception as e:
        logger.error(f"Ошибка при запросе к Claude API: {e}", exc_info=True)

        # AICODE-TODO: Добавить retry с exponential backoff для 429/500 ошибок

        # Fallback ответ
        return {
            "response": "Понял вас! Расскажите подробнее, чтобы я мог лучше помочь.",
            "status": LeadStatus.NEW,
            "action": "continue",
        }
