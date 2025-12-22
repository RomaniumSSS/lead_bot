"""Интеграция с Anthropic Claude API для генерации ответов и квалификации лидов."""

import json
import logging
from typing import Literal, cast

from anthropic import APIStatusError, AsyncAnthropic, RateLimitError
from anthropic.types import Message as AnthropicMessage
from anthropic.types import MessageParam, TextBlock
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

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


@retry(  # type: ignore[misc]
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((RateLimitError, APIStatusError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def _call_claude(  # noqa: PLR0913
    client: AsyncAnthropic,
    model: str,
    max_tokens: int,
    system: str,
    messages: list[MessageParam],
    *,
    use_cache: bool = True,
) -> AnthropicMessage:
    """
    Вызывает Claude API с автоматическими retry при ошибках.

    Retry срабатывает при:
    - RateLimitError (429) — превышен лимит запросов
    - APIStatusError (500+) — ошибки сервера

    Стратегия retry: exponential backoff (2s, 4s, 8s, ..., до 30s).
    Максимум 3 попытки.

    Args:
        client: AsyncAnthropic клиент
        model: Модель Claude
        max_tokens: Максимум токенов в ответе
        system: Системный промпт (строка или список блоков)
        messages: История диалога
        use_cache: Использовать ли prompt caching (по умолчанию True)

    Returns:
        AnthropicMessage с ответом от Claude

    Raises:
        RateLimitError: После 3 неудачных попыток при rate limit
        APIStatusError: После 3 неудачных попыток при ошибке сервера
    """
    # AICODE-NOTE: Prompt caching экономит до 90% токенов на системном промпте.
    # Кэш живёт 5 минут. При повторных запросах Claude использует закэшированный промпт.
    if use_cache:
        system_blocks = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        return await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_blocks,  # type: ignore[arg-type]
            messages=messages,
        )
    return await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )


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
        # Запрос к Claude API с ограниченными токенами и retry
        response = await _call_claude(
            client=client,
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

        # Логируем использование кэша (если есть)
        usage = response.usage
        if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
            logger.info(
                f"Claude FREE_CHAT для лида {lead.id}: cache hit "
                f"({usage.cache_read_input_tokens} cached tokens)"
            )
        else:
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
        # Запрос к Claude API с retry
        response = await _call_claude(
            client=client,
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

        # Логируем использование кэша (если есть)
        usage = response.usage
        if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
            logger.info(
                f"Claude response для лида {lead.id}: cache hit "
                f"({usage.cache_read_input_tokens} cached tokens)"
            )
        else:
            logger.info(f"Claude response для лида {lead.id}: {response_text[:100]}")

        # Парсим JSON ответ
        return _parse_llm_response(response_text, lead.status)

    except Exception as e:
        logger.error(f"Ошибка при запросе к Claude API: {e}", exc_info=True)

        # Fallback ответ
        return {
            "response": "Понял вас! Расскажите подробнее, чтобы я мог лучше помочь.",
            "status": LeadStatus.NEW,
            "action": "continue",
        }


async def parse_custom_meeting_time(text: str) -> dict[str, str] | None:
    """
    Парсит произвольное время встречи через Claude API.

    Примеры входных данных:
    - "завтра в 15:00"
    - "в среду в 11:00"
    - "28 декабря, 14:00"

    Args:
        text: Текст от пользователя с описанием времени

    Returns:
        dict с полями date (YYYY-MM-DD) и time (HH:MM) или None если не удалось распарсить
    """
    from datetime import UTC, datetime

    now = datetime.now(tz=UTC)
    weekdays_ru = [
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    ]
    current_weekday = weekdays_ru[now.weekday()]

    prompt = f"""Сегодня: {current_weekday}, {now.day} {now.strftime('%B')} {now.year} года.
Текущее время: {now.strftime('%H:%M')}.

Пользователь написал: "{text}"

Твоя задача: определить дату и время встречи.

**ВАЖНО:**
- Если указан день недели (например, "в среду") — найди ближайшую среду от сегодня.
- Если указано "завтра" — это {(now.day + 1)} число.
- Если указана конкретная дата — используй её.
- Время должно быть в формате HH:MM (24-часовой формат).

Верни ТОЛЬКО JSON в формате:
{{
    "date": "YYYY-MM-DD",
    "time": "HH:MM",
    "success": true
}}

Если не удалось распознать дату или время, верни:
{{
    "success": false,
    "reason": "Краткое объяснение проблемы"
}}

Примеры:
- "завтра в 15:00" → {{"date": "2025-12-24", "time": "15:00", "success": true}}
- "в пятницу в 10:00" → {{"date": "2025-12-27", "time": "10:00", "success": true}}
- "не знаю" → {{"success": false, "reason": "Не указано время"}}
"""

    try:
        response = await _call_claude(
            client=client,
            model=MODEL,
            max_tokens=128,
            system="Ты — помощник для парсинга дат и времени из естественного языка.",
            messages=[{"role": "user", "content": prompt}],
            use_cache=False,  # Не кэшируем, т.к. промпт меняется (текущая дата)
        )

        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            logger.error(f"Claude вернул неожиданный тип блока: {type(first_block)}")
            return None

        response_text = first_block.text.strip()

        # Очищаем от markdown
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        parsed = json.loads(response_text)

        if not parsed.get("success"):
            logger.warning(f"Claude не смог распарсить время: {parsed.get('reason')}")
            return None

        return {"date": parsed["date"], "time": parsed["time"]}

    except Exception as e:
        logger.error(f"Ошибка при парсинге времени через Claude: {e}", exc_info=True)
        return None


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
