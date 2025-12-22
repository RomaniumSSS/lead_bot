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


# AICODE-NOTE: Используем Claude 4.5 Sonnet - оптимальное соотношение
# скорости и качества для диалогов
MODEL = "claude-sonnet-4-20250514"  # Claude Sonnet 4.5"

# AICODE-NOTE: Ограничиваем количество сообщений истории для экономии токенов
MAX_HISTORY_MESSAGES = 10


async def generate_response_free_chat(lead: Lead, message: str) -> LLMResponse:
    """
    Генерирует ответ бота для свободного диалога (после квалификации).

    Использует сокращённый контекст (последние N сообщений) и
    ограниченные токены для коротких ответов.

    Args:
        lead: Объект лида из БД
        message: Последнее сообщение от лида

    Returns:
        LLMResponse с ответом бота
    """
    # Загружаем последние сообщения диалога (не все, для экономии токенов)
    conversation_history: list[Conversation] = (
        await Conversation.filter(lead=lead).order_by("-created_at").limit(MAX_HISTORY_MESSAGES)
    )
    # Переворачиваем обратно в хронологический порядок
    conversation_history = list(reversed(conversation_history))

    # Формируем сообщения для Claude
    messages: list[MessageParam] = []
    for conv in conversation_history:
        messages.append({"role": conv.role.value, "content": conv.content})

    # Добавляем текущее сообщение (если ещё не в истории)
    if not messages or messages[-1]["content"] != message:
        messages.append({"role": "user", "content": message})

    # Контекст о лиде
    lead_context = ""
    if lead.task:
        lead_context += f"Задача клиента: {lead.task}\n"
    if lead.budget:
        lead_context += f"Бюджет: {lead.budget}\n"
    if lead.deadline:
        lead_context += f"Срок: {lead.deadline}\n"
    if lead.status:
        status_labels = {
            LeadStatus.HOT: "Горячий (готов к встрече)",
            LeadStatus.WARM: "Тёплый (заинтересован)",
            LeadStatus.COLD: "Холодный (пока думает)",
            LeadStatus.NEW: "Новый",
        }
        lead_context += f"Статус: {status_labels.get(lead.status, lead.status.value)}\n"

    # Системный промпт для свободного диалога
    system_prompt: str = f"""Ты — AI-ассистент бизнеса "{settings.business_name}".

{settings.business_description}

**Информация о клиенте:**
{lead_context}

**Твоя задача:**
Помогать клиенту, отвечать на вопросы, давать полезную информацию.

**ВАЖНЫЕ ПРАВИЛА:**
1. Задавай ТОЛЬКО ОДИН вопрос за раз, не несколько сразу.
2. Ответ должен быть КОРОТКИМ (максимум 2-3 предложения).
3. Будь дружелюбным и профессиональным.
4. НЕ повторяй информацию, которую уже знаешь о клиенте.
5. Если клиент готов — предложи назначить встречу.

**Плохой пример:**
"Отлично! Какой у вас бюджет? Когда нужно? Какие есть требования? Что ещё важно?"

**Хороший пример:**
"Понял! Расскажите, какие основные требования к проекту?"

**Формат ответа:**
Отвечай ТОЛЬКО в JSON формате:
{{
    "response": "Твой ответ клиенту (естественный текст, 1-3 предложения)",
    "status": "{lead.status.value.upper()}",
    "action": "continue"
}}
"""

    try:
        # Запрос к Claude API с ограниченными токенами
        response = await client.messages.create(
            model=MODEL,
            max_tokens=256,  # AICODE-NOTE: Ограничиваем до 256 для коротких ответов
            system=system_prompt,
            messages=messages,
        )

        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            logger.error(f"Claude вернул неожиданный тип блока: {type(first_block)}")
            raise ValueError("Expected TextBlock from Claude response")

        response_text: str = first_block.text

        logger.info(f"Claude FREE_CHAT для лида {lead.id}: {response_text[:100]}")

        # Парсим и возвращаем JSON ответ
        return _parse_llm_response(response_text, lead.status)

    except Exception as e:
        logger.error(f"Ошибка при запросе к Claude API: {e}", exc_info=True)

        # Fallback ответ
        return {
            "response": "Понял вас! Если нужна дополнительная информация — спрашивайте.",
            "status": lead.status,
            "action": "continue",
        }


async def generate_response(lead: Lead, message: str) -> LLMResponse:
    """
    Генерирует ответ бота и оценивает статус лида через Claude API.

    DEPRECATED: Используйте generate_response_free_chat для нового flow с FSM.
    Эта функция оставлена для обратной совместимости.

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

    # Загружаем историю диалога (ограничиваем количество)
    conversation_history: list[Conversation] = (
        await Conversation.filter(lead=lead).order_by("-created_at").limit(MAX_HISTORY_MESSAGES)
    )
    conversation_history = list(reversed(conversation_history))

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

**ВАЖНЫЕ ПРАВИЛА:**
1. Задавай ТОЛЬКО ОДИН вопрос за раз, а не несколько сразу.
2. Вопрос должен быть КОНКРЕТНЫМ и КОРОТКИМ (максимум 2 предложения).
3. НЕ дублируй информацию, которую уже знаешь.
4. Используй дружелюбный тон, но будь лаконичен.

**Плохой пример:**
"Отлично! Какой у вас бюджет? Когда нужно? Какие есть требования?"

**Хороший пример:**
"Какой у вас примерный бюджет на проект?"

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
            max_tokens=256,  # AICODE-NOTE: Уменьшено с 1024 до 256 для коротких ответов
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
        return _parse_llm_response(response_text, lead.status)

    except Exception as e:
        logger.error(f"Ошибка при запросе к Claude API: {e}", exc_info=True)

        # AICODE-TODO: Добавить retry с exponential backoff для 429/500 ошибок

        # Fallback ответ
        return {
            "response": "Понял вас! Расскажите подробнее, чтобы я мог лучше помочь.",
            "status": LeadStatus.NEW,
            "action": "continue",
        }


def _parse_llm_response(response_text: str, default_status: LeadStatus) -> LLMResponse:
    """Парсит JSON ответ от Claude.

    Args:
        response_text: Текст ответа от Claude
        default_status: Статус по умолчанию, если парсинг не удался

    Returns:
        LLMResponse
    """
    # AICODE-NOTE: Claude иногда оборачивает JSON в markdown (```json ... ```)
    # Очищаем от markdown-блоков перед парсингом
    cleaned_text = response_text.strip()
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:]  # Убираем ```json
    elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:]  # Убираем ```
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]  # Убираем закрывающие ```
    cleaned_text = cleaned_text.strip()

    # Парсим JSON ответ
    try:
        parsed: LLMResponseRaw = json.loads(cleaned_text)
    except json.JSONDecodeError:
        # AICODE-TODO: Иногда Claude возвращает не чистый JSON. Нужен fallback парсинг.
        logger.warning(f"Claude вернул не JSON: {response_text}")
        # Простой fallback
        return {
            "response": response_text,
            "status": default_status,
            "action": "continue",
        }

    # Конвертируем статус в Enum
    status_str: str = parsed.get("status", "NEW").upper()
    try:
        status: LeadStatus = LeadStatus[status_str]
    except KeyError:
        logger.warning(f"Неизвестный статус от Claude: {status_str}, используем default")
        status = default_status

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
