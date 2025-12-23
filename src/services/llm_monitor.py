"""Мониторинг использования LLM API."""

from datetime import UTC, datetime, timedelta

from anthropic.types import Usage

from src.database.models import Lead, LLMUsage
from src.utils.logger import logger

# AICODE-NOTE: Тарифы Claude (в USD за 1M токенов)
# Актуально на декабрь 2024. Если тарифы изменятся — обновить здесь.
# Источник: https://www.anthropic.com/pricing
PRICING = {
    "claude-sonnet-4-20250514": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-3-5-haiku-20241022": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
}


async def track_llm_usage(
    model: str,
    usage: Usage,
    request_type: str,
    lead: Lead | None = None,
) -> None:
    """
    Сохраняет статистику использования LLM в БД.

    Args:
        model: Модель Claude (напр. "claude-sonnet-4-20250514")
        usage: Объект Usage от Claude API
        request_type: Тип запроса (greeting, free_chat, suggested_questions, etc.)
        lead: Объект лида (если есть)
    """
    # Получаем тарифы для модели (или используем тарифы Sonnet по умолчанию)
    pricing = PRICING.get(model, PRICING["claude-sonnet-4-20250514"])

    # Считаем стоимость (в центах)
    cost_input = int((usage.input_tokens / 1_000_000) * pricing["input"] * 100)
    cost_output = int((usage.output_tokens / 1_000_000) * pricing["output"] * 100)

    # AICODE-NOTE: cache_creation_input_tokens и cache_read_input_tokens могут отсутствовать
    # если prompt caching не использовался
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0)

    cost_cache_creation = int((cache_creation / 1_000_000) * pricing["cache_write"] * 100)
    cost_cache_read = int((cache_read / 1_000_000) * pricing["cache_read"] * 100)

    total_cost = cost_input + cost_output + cost_cache_creation + cost_cache_read

    # Сохраняем в БД
    try:
        await LLMUsage.create(
            lead=lead,
            model=model,
            request_type=request_type,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_tokens=cache_creation,
            cache_read_tokens=cache_read,
            cost_input=cost_input,
            cost_output=cost_output,
            cost_cache_creation=cost_cache_creation,
            cost_cache_read=cost_cache_read,
            total_cost=total_cost,
        )

        # Логируем только если стоимость > 0 (для экономии места в логах)
        if total_cost > 0:
            logger.info(
                f"💰 LLM Usage: {request_type} | "
                f"tokens={usage.input_tokens + usage.output_tokens} | "
                f"cost=${total_cost / 100:.4f} | "
                f"cache_hit={cache_read > 0}"
            )
    except Exception as e:
        # AICODE-NOTE: Не падаем если не удалось сохранить статистику
        logger.error(f"Ошибка сохранения LLM usage: {e}", exc_info=True)


async def get_daily_stats() -> dict[str, int | float]:
    """
    Возвращает статистику использования LLM за сегодня.

    Returns:
        dict со статистикой:
            - total_requests: количество запросов
            - input_tokens: количество input токенов
            - output_tokens: количество output токенов
            - cache_hit_rate: процент кэш-хитов
            - total_cost: общая стоимость в центах
            - sonnet_requests: количество запросов к Sonnet
            - sonnet_cost: стоимость Sonnet в центах
            - haiku_requests: количество запросов к Haiku
            - haiku_cost: стоимость Haiku в центах
    """
    # Текущая дата (начало дня по UTC)
    today_start = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # Все записи за сегодня
    usage_records = await LLMUsage.filter(created_at__gte=today_start).all()

    if not usage_records:
        return {
            "total_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_hit_rate": 0.0,
            "total_cost": 0,
            "sonnet_requests": 0,
            "sonnet_cost": 0,
            "haiku_requests": 0,
            "haiku_cost": 0,
        }

    # Агрегация
    total_requests = len(usage_records)
    input_tokens = sum(r.input_tokens for r in usage_records)
    output_tokens = sum(r.output_tokens for r in usage_records)
    total_cost = sum(r.total_cost for r in usage_records)

    # Cache hit rate
    cache_read_tokens = sum(r.cache_read_tokens for r in usage_records)
    total_input_tokens = input_tokens + cache_read_tokens
    cache_hit_rate = (
        (cache_read_tokens / total_input_tokens * 100) if total_input_tokens > 0 else 0.0
    )

    # Статистика по моделям
    sonnet_records = [r for r in usage_records if "sonnet" in r.model.lower()]
    haiku_records = [r for r in usage_records if "haiku" in r.model.lower()]

    sonnet_requests = len(sonnet_records)
    sonnet_cost = sum(r.total_cost for r in sonnet_records)

    haiku_requests = len(haiku_records)
    haiku_cost = sum(r.total_cost for r in haiku_records)

    return {
        "total_requests": total_requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_hit_rate": cache_hit_rate,
        "total_cost": total_cost,
        "sonnet_requests": sonnet_requests,
        "sonnet_cost": sonnet_cost,
        "haiku_requests": haiku_requests,
        "haiku_cost": haiku_cost,
    }


async def get_lead_stats(lead: Lead) -> dict[str, int | float]:
    """
    Возвращает статистику использования LLM по конкретному лиду.

    Args:
        lead: Объект лида

    Returns:
        dict со статистикой:
            - total_requests: количество запросов
            - input_tokens: количество input токенов
            - output_tokens: количество output токенов
            - total_cost: общая стоимость в центах
    """
    usage_records = await LLMUsage.filter(lead=lead).all()

    if not usage_records:
        return {
            "total_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_cost": 0,
        }

    total_requests = len(usage_records)
    input_tokens = sum(r.input_tokens for r in usage_records)
    output_tokens = sum(r.output_tokens for r in usage_records)
    total_cost = sum(r.total_cost for r in usage_records)

    return {
        "total_requests": total_requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_cost": total_cost,
    }


async def get_weekly_stats() -> dict[str, int | float]:
    """
    Возвращает статистику использования LLM за последние 7 дней.

    Returns:
        dict со статистикой (аналогично get_daily_stats)
    """
    week_start = datetime.now(tz=UTC) - timedelta(days=7)

    usage_records = await LLMUsage.filter(created_at__gte=week_start).all()

    if not usage_records:
        return {
            "total_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_hit_rate": 0.0,
            "total_cost": 0,
            "sonnet_requests": 0,
            "sonnet_cost": 0,
            "haiku_requests": 0,
            "haiku_cost": 0,
        }

    total_requests = len(usage_records)
    input_tokens = sum(r.input_tokens for r in usage_records)
    output_tokens = sum(r.output_tokens for r in usage_records)
    total_cost = sum(r.total_cost for r in usage_records)

    cache_read_tokens = sum(r.cache_read_tokens for r in usage_records)
    total_input_tokens = input_tokens + cache_read_tokens
    cache_hit_rate = (
        (cache_read_tokens / total_input_tokens * 100) if total_input_tokens > 0 else 0.0
    )

    sonnet_records = [r for r in usage_records if "sonnet" in r.model.lower()]
    haiku_records = [r for r in usage_records if "haiku" in r.model.lower()]

    sonnet_requests = len(sonnet_records)
    sonnet_cost = sum(r.total_cost for r in sonnet_records)

    haiku_requests = len(haiku_records)
    haiku_cost = sum(r.total_cost for r in haiku_records)

    return {
        "total_requests": total_requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_hit_rate": cache_hit_rate,
        "total_cost": total_cost,
        "sonnet_requests": sonnet_requests,
        "sonnet_cost": sonnet_cost,
        "haiku_requests": haiku_requests,
        "haiku_cost": haiku_cost,
    }
