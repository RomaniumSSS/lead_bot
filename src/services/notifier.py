"""Сервис уведомлений владельцу бизнеса."""

from aiogram import Bot

from src.config import settings
from src.database.models import Lead, LeadStatus, Meeting
from src.utils.logger import logger


async def notify_owner_about_lead(lead: Lead) -> None:
    """
    Отправляет уведомление владельцу о новом квалифицированном лиде.

    Args:
        lead: Объект лида из БД
    """
    # Уведомляем только о горячих и тёплых лидах
    if lead.status not in [LeadStatus.HOT, LeadStatus.WARM]:
        return

    # Проверяем что owner_telegram_id настроен
    if settings.owner_telegram_id is None:
        logger.warning("OWNER_TELEGRAM_ID не настроен, пропускаем уведомление")
        return

    # AICODE-TODO: Вынести создание Bot() в глобальный контекст (сейчас создаём каждый раз)
    bot: Bot = Bot(token=settings.telegram_bot_token)

    try:
        # Формируем эмодзи и текст в зависимости от статуса
        emoji: str
        status_text: str
        if lead.status == LeadStatus.HOT:
            emoji = "🔥"
            status_text = "ГОРЯЧИЙ"
        elif lead.status == LeadStatus.WARM:
            emoji = "🟡"
            status_text = "ТЁПЛЫЙ"
        else:
            emoji = "⚪️"
            status_text = "Новый"

        # Имя лида
        lead_name: str = lead.first_name or lead.username or f"User {lead.telegram_id}"

        # Формируем текст уведомления
        notification: str = f"{emoji} **Новый {status_text} лид!**\n\n👤 **Имя**: {lead_name}\n"

        if lead.task:
            notification += f"📋 **Задача**: {lead.task}\n"

        if lead.budget:
            notification += f"💰 **Бюджет**: {lead.budget}\n"

        if lead.deadline:
            notification += f"⏰ **Срок**: {lead.deadline}\n"

        # Ссылка на пользователя
        if lead.username:
            notification += f"\n**Telegram**: @{lead.username}"
        else:
            notification += f"\n**Telegram ID**: `{lead.telegram_id}`"

        # Отправляем уведомление владельцу
        await bot.send_message(
            chat_id=settings.owner_telegram_id, text=notification, parse_mode="Markdown"
        )

        logger.info(f"Уведомление о лиде {lead} отправлено владельцу")

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления владельцу о лиде {lead}: {e}", exc_info=True)

    finally:
        await bot.session.close()


async def notify_owner_meeting_scheduled(lead: Lead, meeting: Meeting) -> None:
    """
    Отправляет уведомление владельцу о назначенной встрече.

    Args:
        lead: Объект лида из БД
        meeting: Объект встречи из БД
    """
    # Проверяем что owner_telegram_id настроен
    if settings.owner_telegram_id is None:
        logger.warning("OWNER_TELEGRAM_ID не настроен, пропускаем уведомление о встрече")
        return

    bot: Bot = Bot(token=settings.telegram_bot_token)

    try:
        # Имя лида
        lead_name: str = lead.first_name or lead.username or f"User {lead.telegram_id}"

        # Форматируем время встречи
        time_str = meeting.scheduled_at.strftime("%d.%m.%Y в %H:%M")

        # Формируем текст уведомления
        notification = (
            f"📅 **Новая встреча назначена!**\n\n"
            f"👤 **Имя**: {lead_name}\n"
            f"⏰ **Время**: {time_str}\n"
        )

        # Добавляем информацию о задаче, бюджете, сроке (если есть)
        if lead.task:
            notification += f"📋 **Задача**: {lead.task}\n"

        if lead.budget:
            notification += f"💰 **Бюджет**: {lead.budget}\n"

        if lead.deadline:
            notification += f"⏳ **Срок**: {lead.deadline}\n"

        # Ссылка на пользователя
        if lead.username:
            notification += f"\n**Telegram**: @{lead.username}"
        else:
            notification += f"\n**Telegram ID**: `{lead.telegram_id}`"

        # Отправляем уведомление владельцу
        await bot.send_message(
            chat_id=settings.owner_telegram_id, text=notification, parse_mode="Markdown"
        )

        logger.info(f"Уведомление о встрече {meeting.id} для лида {lead.id} отправлено владельцу")

    except Exception as e:
        logger.error(
            f"Ошибка при отправке уведомления владельцу о встрече {meeting.id}: {e}", exc_info=True
        )

    finally:
        await bot.session.close()
