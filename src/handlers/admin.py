"""Handler для команд владельца бизнеса (admin)."""

from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import settings
from src.database.models import Lead, LeadStatus, Meeting, MeetingStatus
from src.services.llm_monitor import get_daily_stats, get_weekly_stats
from src.utils.logger import logger

router = Router(name="admin")


def is_owner(message: Message) -> bool:
    """Проверяет, что сообщение от владельца."""
    return message.from_user is not None and message.from_user.id == settings.owner_telegram_id


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """
    Отправляет статистику владельцу.
    Доступна только для OWNER_TELEGRAM_ID.
    """
    if not is_owner(message):
        user_id = message.from_user.id if message.from_user else "Unknown"
        logger.warning(f"Попытка доступа к /stats от не-владельца: {user_id}")
        await message.answer("❌ У вас нет доступа к этой команде.")
        return

    # AICODE-TODO: Оптимизировать запросы (использовать один агрегирующий запрос)

    # Статистика за сегодня
    today_start: datetime = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Всего лидов
    total_leads: int = await Lead.all().count()

    # Лиды за сегодня
    today_leads: int = await Lead.filter(created_at__gte=today_start).count()

    # По статусам (всего)
    hot_leads: int = await Lead.filter(status=LeadStatus.HOT).count()
    warm_leads: int = await Lead.filter(status=LeadStatus.WARM).count()
    cold_leads: int = await Lead.filter(status=LeadStatus.COLD).count()
    new_leads: int = await Lead.filter(status=LeadStatus.NEW).count()

    # Встречи
    scheduled_meetings: int = await Meeting.filter(status=MeetingStatus.SCHEDULED).count()

    # Последний горячий лид
    last_hot_lead: Lead | None = (
        await Lead.filter(status=LeadStatus.HOT).order_by("-updated_at").first()
    )
    last_hot_info: str = ""
    if last_hot_lead:
        last_hot_name: str = (
            last_hot_lead.first_name
            or last_hot_lead.username
            or f"User {last_hot_lead.telegram_id}"
        )
        last_hot_time: str = last_hot_lead.updated_at.strftime("%H:%M")
        last_hot_info = f"\n\n🔥 Последний горячий лид: **{last_hot_name}**, {last_hot_time}"

    stats_text = (
        f"📊 **Статистика**\n\n"
        f"📈 Всего лидов: **{total_leads}**\n"
        f"🆕 Новых за сегодня: **{today_leads}**\n\n"
        f"**По статусам:**\n"
        f"🔥 Горячих: **{hot_leads}**\n"
        f"🟡 Тёплых: **{warm_leads}**\n"
        f"❄️ Холодных: **{cold_leads}**\n"
        f"⚪️ Новых: **{new_leads}**\n\n"
        f"📅 Назначено встреч: **{scheduled_meetings}**"
        f"{last_hot_info}"
    )

    await message.answer(stats_text)
    owner_id = message.from_user.id if message.from_user else settings.owner_telegram_id
    logger.info(f"Статистика отправлена владельцу: {owner_id}")


@router.message(Command("llm_stats"))
async def cmd_llm_stats(message: Message) -> None:
    """
    Команда /llm_stats - статистика использования LLM (только для владельца).

    Показывает:
    - Количество запросов за сегодня и за неделю
    - Токены (input/output)
    - Cache hit rate
    - Стоимость
    - Разбивку по моделям (Sonnet vs Haiku)
    """
    if not is_owner(message):
        user_id = message.from_user.id if message.from_user else "Unknown"
        logger.warning(f"Попытка доступа к /llm_stats от не-владельца: {user_id}")
        await message.answer("❌ У вас нет доступа к этой команде.")
        return

    user_id = message.from_user.id if message.from_user else "Unknown"
    logger.info(f"Команда /llm_stats от владельца: {user_id}")

    # Получаем статистику
    daily_stats = await get_daily_stats()
    weekly_stats = await get_weekly_stats()

    # Формируем текст
    stats_text = f"""📊 **Статистика LLM**

**За сегодня:**
🔹 Запросов: {daily_stats['total_requests']}
🔹 Токенов (input): {daily_stats['input_tokens']:,}
🔹 Токенов (output): {daily_stats['output_tokens']:,}
🔹 Cache hit rate: {daily_stats['cache_hit_rate']:.1f}%

💰 **Стоимость**: ${daily_stats['total_cost'] / 100:.4f}

**По моделям (сегодня):**
- Sonnet: {daily_stats['sonnet_requests']} запросов (${daily_stats['sonnet_cost'] / 100:.4f})
- Haiku: {daily_stats['haiku_requests']} запросов (${daily_stats['haiku_cost'] / 100:.4f})

---

**За последние 7 дней:**
🔹 Запросов: {weekly_stats['total_requests']}
🔹 Токенов (input): {weekly_stats['input_tokens']:,}
🔹 Токенов (output): {weekly_stats['output_tokens']:,}
🔹 Cache hit rate: {weekly_stats['cache_hit_rate']:.1f}%

💰 **Стоимость**: ${weekly_stats['total_cost'] / 100:.4f}

**По моделям (неделя):**
- Sonnet: {weekly_stats['sonnet_requests']} запросов (${weekly_stats['sonnet_cost'] / 100:.4f})
- Haiku: {weekly_stats['haiku_requests']} запросов (${weekly_stats['haiku_cost'] / 100:.4f})
"""

    await message.answer(stats_text)
    user_id = message.from_user.id if message.from_user else "Unknown"
    logger.info(f"LLM статистика отправлена владельцу: {user_id}")
