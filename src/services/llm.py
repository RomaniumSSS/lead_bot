"""Интеграция с Anthropic Claude API для генерации ответов и квалификации лидов."""

import json
import logging
from datetime import UTC, datetime
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
from src.services.llm_monitor import track_llm_usage
from src.types import LLMResponse, LLMResponseRaw
from src.utils.logger import logger

# Инициализация Claude API клиента
client = AsyncAnthropic(api_key=settings.anthropic_api_key)


# AICODE-NOTE: Используем Claude 4.5 Sonnet - оптимальное соотношение
# скорости и качества для диалогов
MODEL = "claude-sonnet-4-20250514"  # Claude Sonnet 4.5"

# AICODE-NOTE: Haiku для простых задач (приветствия, короткие тексты) — дешевле
MODEL_HAIKU = "claude-3-5-haiku-20241022"  # Claude 3.5 Haiku (актуальная версия)

# AICODE-NOTE: Ограничиваем количество сообщений истории для экономии токенов
MAX_HISTORY_MESSAGES = 10


@retry(
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

        # Трекинг использования LLM
        await track_llm_usage(
            model=MODEL,
            usage=response.usage,
            request_type="free_chat",
            lead=lead,
        )

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

        # Трекинг использования LLM
        await track_llm_usage(
            model=MODEL,
            usage=response.usage,
            request_type="qualification",
            lead=lead,
        )

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


async def generate_suggested_questions(lead: Lead) -> list[str]:
    """
    Генерирует 3-4 релевантных вопроса на основе контекста лида через Claude.

    Args:
        lead: Объект лида из БД

    Returns:
        Список из 3-4 предложенных вопросов
    """
    # Формируем контекст о лиде
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

    # Системный промпт
    system_prompt = f"""Ты — AI-ассистент бизнеса "{settings.business_name}".

{settings.business_description}

**Твоя задача:**
На основе информации о клиенте предложить 3-4 релевантных вопроса, которые клиент может задать.

**Информация о клиенте:**
{lead_context if lead_context else "Минимальная информация"}

**ВАЖНЫЕ ПРАВИЛА:**
1. Вопросы должны быть КОНКРЕТНЫМИ и ПОЛЕЗНЫМИ для данного клиента.
2. Учитывай контекст: задачу, бюджет, срок, статус.
3. Вопросы должны помогать клиенту двигаться к решению (понять стоимость, сроки, процесс).
4. Формулируй от первого лица клиента (как будто он спрашивает).
5. КРАТКИЕ вопросы (максимум 8-10 слов).

**Примеры хороших вопросов:**
- "Сколько времени займёт работа?"
- "Можно разбить оплату на этапы?"
- "Покажете примеры похожих проектов?"
- "Какие гарантии вы даёте?"

**Плохие примеры (слишком общие):**
- "Расскажите о вашей компании"
- "Что вы делаете?"

**Формат ответа:**
Верни ТОЛЬКО JSON в формате:
{{
    "questions": ["Вопрос 1", "Вопрос 2", "Вопрос 3", "Вопрос 4"]
}}

Количество вопросов: ровно 3 или 4."""

    try:
        # Запрос к Claude API
        response = await _call_claude(
            client=client,
            model=MODEL,
            max_tokens=256,
            system=system_prompt,
            messages=[
                {"role": "user", "content": "Предложи релевантные вопросы для этого клиента."}
            ],
            use_cache=True,  # Кэшируем системный промпт
        )

        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            logger.error(f"Claude вернул неожиданный тип блока: {type(first_block)}")
            return _get_fallback_questions(lead.status)

        response_text = first_block.text.strip()

        # Трекинг использования LLM
        await track_llm_usage(
            model=MODEL,
            usage=response.usage,
            request_type="suggested_questions",
            lead=lead,
        )

        # Очищаем от markdown
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Парсим JSON
        parsed = json.loads(response_text)
        questions: list[str] = parsed.get("questions", [])

        # Валидация: должно быть 3-4 вопроса
        if not questions or len(questions) < 3:
            logger.warning(f"Claude вернул недостаточно вопросов: {questions}")
            return _get_fallback_questions(lead.status)

        # Обрезаем до 4 вопросов
        return questions[:4]

    except Exception as e:
        logger.error(f"Ошибка при генерации вопросов через Claude: {e}", exc_info=True)
        return _get_fallback_questions(lead.status)


def _get_fallback_questions(status: LeadStatus) -> list[str]:
    """Возвращает fallback вопросы на основе статуса лида.

    Args:
        status: Статус лида

    Returns:
        Список из 3-4 предопределённых вопросов
    """
    # AICODE-NOTE: Fallback на случай если Claude не сгенерирует вопросы
    if status == LeadStatus.HOT:
        return [
            "Когда можем созвониться?",
            "Какие документы нужны для старта?",
            "Можно обсудить детали сегодня?",
        ]
    if status == LeadStatus.WARM:
        return [
            "Сколько займёт работа?",
            "Можно разбить оплату на этапы?",
            "Покажете примеры работ?",
        ]
    # COLD или NEW
    return [
        "Какие услуги вы предлагаете?",
        "Сколько стоят ваши услуги?",
        "Как проходит работа?",
    ]


async def generate_lead_summary(lead: Lead) -> str:
    """
    Генерирует краткое резюме диалога с лидом для владельца бизнеса.

    Args:
        lead: Объект лида из БД

    Returns:
        Краткое резюме (2-3 предложения)
    """
    # Загружаем последние сообщения диалога (последние 20 для контекста)
    conversation_history: list[Conversation] = (
        await Conversation.filter(lead=lead).order_by("-created_at").limit(20)
    )
    conversation_history = list(reversed(conversation_history))

    # Формируем историю диалога для контекста
    dialogue_text = ""
    for conv in conversation_history[-10:]:  # Берём последние 10 для компактности
        role_name = "Клиент" if conv.role.value == "user" else "Бот"
        dialogue_text += f"{role_name}: {conv.content}\n"

    # Формируем контекст о лиде
    lead_context = ""
    if lead.task:
        lead_context += f"Задача: {lead.task}\n"
    if lead.budget:
        lead_context += f"Бюджет: {lead.budget}\n"
    if lead.deadline:
        lead_context += f"Срок: {lead.deadline}\n"
    if lead.status:
        status_labels = {
            LeadStatus.HOT: "Горячий",
            LeadStatus.WARM: "Тёплый",
            LeadStatus.COLD: "Холодный",
            LeadStatus.NEW: "Новый",
        }
        lead_context += f"Статус: {status_labels.get(lead.status, lead.status.value)}\n"

    # Системный промпт
    system_prompt = f"""Ты — AI-ассистент для владельца бизнеса "{settings.business_name}".

{settings.business_description}

**Твоя задача:**
Создать КРАТКОЕ резюме диалога с клиентом для владельца бизнеса.

**ВАЖНЫЕ ПРАВИЛА:**
1. Резюме должно быть ОЧЕНЬ КОРОТКИМ: 2-3 предложения (максимум 150 символов).
2. Включай только КЛЮЧЕВУЮ информацию: что хочет клиент, бюджет, срок, уровень готовности.
3. Пиши деловым тоном, БЕЗ воды и лишних слов.
4. Если клиент готов к встрече — обязательно укажи это.
5. НЕ повторяй очевидное из структурированных данных.

**Информация о клиенте:**
{lead_context}

**История диалога (последние сообщения):**
{dialogue_text if dialogue_text else "Нет сообщений"}

**Формат ответа:**
Верни ТОЛЬКО JSON в формате:
{{
    "summary": "Краткое резюме в 2-3 предложения"
}}

**Примеры хороших резюме:**
- "Ищет разработку корпоративного сайта с CRM. Бюджет 150к, запуск через 2 недели.
  Готов обсудить сегодня."
- "Интересуется дизайном для кафе. Средний бюджет, срок нормальный.
  Хочет посмотреть примеры работ."
- "Спрашивал про услуги, но пока не определился с задачей и бюджетом."

**Плохие примеры (слишком длинные, вода):**
- "Клиент написал нам и рассказал, что он хочет разработать сайт.
  Он сказал, что у него есть бюджет..."
"""

    try:
        # Запрос к Claude API
        response = await _call_claude(
            client=client,
            model=MODEL,
            max_tokens=128,  # Короткое резюме
            system=system_prompt,
            messages=[{"role": "user", "content": "Создай краткое резюме для владельца."}],
            use_cache=True,  # Кэшируем системный промпт
        )

        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            logger.error(f"Claude вернул неожиданный тип блока: {type(first_block)}")
            return _get_fallback_summary(lead)

        response_text = first_block.text.strip()

        # Трекинг использования LLM
        await track_llm_usage(
            model=MODEL,
            usage=response.usage,
            request_type="lead_summary",
            lead=lead,
        )

        # Очищаем от markdown
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Парсим JSON
        parsed = json.loads(response_text)
        summary: str = parsed.get("summary", "")

        if summary:
            # Успешно сгенерировано резюме
            return summary

        # Пустое резюме — используем fallback
        logger.warning(f"Claude вернул пустое резюме для лида {lead.id}")
        return _get_fallback_summary(lead)

    except Exception as e:
        logger.error(f"Ошибка при генерации резюме через Claude: {e}", exc_info=True)
        return _get_fallback_summary(lead)


def _get_fallback_summary(lead: Lead) -> str:
    """Возвращает fallback резюме на основе данных лида.

    Args:
        lead: Объект лида

    Returns:
        Простое резюме на основе структурированных данных
    """
    # AICODE-NOTE: Fallback на случай если Claude не сгенерирует резюме
    parts = []

    if lead.task:
        parts.append(f"Задача: {lead.task}")

    if lead.budget:
        parts.append(f"Бюджет: {lead.budget}")

    if lead.deadline:
        parts.append(f"Срок: {lead.deadline}")

    if not parts:
        return "Новый лид, информация уточняется."

    return ". ".join(parts) + "."


async def generate_greeting(lead: Lead) -> str:
    """
    Генерирует персонализированное приветствие для лида.

    Использует Claude Haiku (дешевле) для генерации короткого приветствия
    на основе времени суток и имени пользователя.

    Args:
        lead: Объект лида из БД

    Returns:
        Персонализированное приветствие (2-3 предложения)
    """
    now = datetime.now(tz=UTC)
    hour = now.hour

    # Определяем время суток
    if 5 <= hour < 12:
        time_of_day = "утро"
        greeting_word = "Доброе утро"
    elif 12 <= hour < 17:
        time_of_day = "день"
        greeting_word = "Добрый день"
    elif 17 <= hour < 22:
        time_of_day = "вечер"
        greeting_word = "Добрый вечер"
    else:
        time_of_day = "ночь"
        greeting_word = "Доброй ночи"

    # Имя лида
    lead_name = lead.first_name or lead.username or "друг"

    # Определяем, возвращается ли лид
    is_returning = lead.status != LeadStatus.NEW or (lead.task is not None)

    # Системный промпт
    system_prompt = f"""Ты — AI-ассистент бизнеса "{settings.business_name}".

{settings.business_description}

**Твоя задача:**
Создать КОРОТКОЕ дружелюбное приветствие для клиента.

**Контекст:**
- Время суток: {time_of_day} ({greeting_word})
- Имя клиента: {lead_name}
- {"Клиент возвращается (уже общался с нами)" if is_returning else "Новый клиент"}

**ВАЖНЫЕ ПРАВИЛА:**
1. Приветствие должно быть ОЧЕНЬ КОРОТКИМ: 1-2 предложения (максимум 100 символов).
2. Используй время суток естественно (не обязательно говорить "{greeting_word}").
3. Тон: дружелюбный, профессиональный, тёплый, но не навязчивый.
4. НЕ дублируй информацию, которая будет в основном сообщении.
5. {"Упомяни что рад снова видеть" if is_returning else "Приветствуй как нового клиента"}.

**Формат ответа:**
Верни ТОЛЬКО JSON в формате:
{{
    "greeting": "Короткое приветствие в 1-2 предложения"
}}

**Примеры хороших приветствий:**
- "Доброе утро, Иван! 👋 Рад помочь!"
- "Привет, Мария! Снова рад видеть. Чем помочь?"
- "Добрый вечер! Готов ответить на вопросы."

**Плохие примеры (слишком длинные):**
- "Доброе утро, Иван! Я AI-ассистент компании WebStudio. Мы занимаемся разработкой..."
"""

    try:
        # Запрос к Claude Haiku (дешевле для простых задач)
        response = await _call_claude(
            client=client,
            model=MODEL_HAIKU,  # Используем Haiku для экономии
            max_tokens=64,  # Очень короткий ответ
            system=system_prompt,
            messages=[{"role": "user", "content": "Создай приветствие."}],
            use_cache=False,  # Не кэшируем — каждое приветствие уникально (время меняется)
        )

        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            logger.error(f"Claude вернул неожиданный тип блока: {type(first_block)}")
            return _get_fallback_greeting(greeting_word, lead_name, is_returning)

        response_text = first_block.text.strip()

        # Очищаем от markdown
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Парсим JSON
        parsed = json.loads(response_text)
        greeting: str = parsed.get("greeting", "")

        # Трекинг использования LLM
        await track_llm_usage(
            model=MODEL_HAIKU,
            usage=response.usage,
            request_type="greeting",
            lead=lead,
        )

        if greeting:
            return greeting

        # Пустое приветствие — используем fallback
        logger.warning(f"Claude вернул пустое приветствие для лида {lead.id}")
        return _get_fallback_greeting(greeting_word, lead_name, is_returning)

    except Exception as e:
        logger.error(f"Ошибка при генерации приветствия через Claude: {e}", exc_info=True)
        return _get_fallback_greeting(greeting_word, lead_name, is_returning)


def _get_fallback_greeting(greeting_word: str, name: str, is_returning: bool) -> str:
    """Возвращает fallback приветствие.

    Args:
        greeting_word: Приветствие в зависимости от времени суток
        name: Имя лида
        is_returning: Возвращается ли лид

    Returns:
        Простое приветствие
    """
    # AICODE-NOTE: Fallback на случай если Claude не сгенерирует приветствие
    if is_returning:
        return f"Привет, {name}! 👋 Снова рад видеть!"
    return f"{greeting_word}, {name}! 👋"


async def generate_followup_message(lead: Lead, days_since_last: int) -> str:
    """
    Генерирует персонализированное follow-up сообщение для лида.

    Args:
        lead: Объект лида из БД
        days_since_last: Количество дней с последнего сообщения

    Returns:
        Follow-up сообщение (2-3 предложения)
    """
    # Формируем контекст о лиде
    lead_context = ""
    if lead.task:
        lead_context += f"Задача клиента: {lead.task}\n"
    if lead.budget:
        lead_context += f"Бюджет: {lead.budget}\n"
    if lead.status:
        status_labels = {
            LeadStatus.HOT: "Горячий (готов к встрече)",
            LeadStatus.WARM: "Тёплый (заинтересован)",
            LeadStatus.COLD: "Холодный (пока думает)",
            LeadStatus.NEW: "Новый",
        }
        lead_context += f"Статус: {status_labels.get(lead.status, lead.status.value)}\n"

    # Имя лида
    lead_name = lead.first_name or lead.username or "друг"

    # Системный промпт
    system_prompt = f"""Ты — AI-ассистент бизнеса "{settings.business_name}".

{settings.business_description}

**Твоя задача:**
Создать МЯГКОЕ напоминание для клиента, который не отвечал {days_since_last} дней.

**Информация о клиенте:**
{lead_context if lead_context else "Минимальная информация"}

**ВАЖНЫЕ ПРАВИЛА:**
1. Сообщение должно быть КОРОТКИМ: 2-3 предложения (максимум 150 символов).
2. Тон: дружелюбный, ненавязчивый, мягкий.
3. НЕ давить на клиента — просто напомнить о себе.
4. Предложить помощь, если вопросы остались актуальны.
5. {"Упомяни задачу клиента" if lead.task else "Будь общим"}.

**Формат ответа:**
Верни ТОЛЬКО JSON в формате:
{{
    "message": "Короткое follow-up сообщение в 2-3 предложения"
}}

**Примеры хороших follow-up:**
- "Привет! 👋 Вижу, вы интересовались дизайном сайта. Если актуально — с радостью
  отвечу на вопросы!"
- "Здравствуйте! Если вопрос по разработке всё ещё актуален — готов помочь."
- "Привет! Напоминаю о себе. Если нужна помощь — пишите!"

**Плохие примеры (слишком навязчиво):**
- "Почему вы не отвечаете? Давайте назначим встречу!"
"""

    try:
        # Запрос к Claude Haiku
        response = await _call_claude(
            client=client,
            model=MODEL_HAIKU,
            max_tokens=128,
            system=system_prompt,
            messages=[{"role": "user", "content": "Создай follow-up сообщение."}],
            use_cache=True,  # Кэшируем системный промпт
        )

        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            logger.error(f"Claude вернул неожиданный тип блока: {type(first_block)}")
            return _get_fallback_followup(lead_name, lead.task)

        response_text = first_block.text.strip()

        # Очищаем от markdown
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Парсим JSON
        parsed = json.loads(response_text)
        message: str = parsed.get("message", "")

        # Трекинг использования LLM
        await track_llm_usage(
            model=MODEL_HAIKU,
            usage=response.usage,
            request_type="followup",
            lead=lead,
        )

        if message:
            return message

        # Пустое сообщение — используем fallback
        logger.warning(f"Claude вернул пустое follow-up для лида {lead.id}")
        return _get_fallback_followup(lead_name, lead.task)

    except Exception as e:
        logger.error(f"Ошибка при генерации follow-up через Claude: {e}", exc_info=True)
        return _get_fallback_followup(lead_name, lead.task)


def _get_fallback_followup(name: str, task: str | None) -> str:
    """Возвращает fallback follow-up сообщение.

    Args:
        name: Имя лида
        task: Задача лида (если есть)

    Returns:
        Простое follow-up сообщение
    """
    # AICODE-NOTE: Fallback на случай если Claude не сгенерирует follow-up
    if task:
        return (
            f"Привет, {name}! 👋\n\n"
            f"Вижу, вы интересовались: {task}.\n"
            f"Если актуально — с радостью помогу!"
        )
    return f"Привет, {name}! 👋\n\nНапоминаю о себе. Если есть вопросы — пишите!"


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

        # Трекинг использования LLM (без привязки к лиду)
        await track_llm_usage(
            model=MODEL,
            usage=response.usage,
            request_type="parse_meeting_time",
            lead=None,
        )

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
