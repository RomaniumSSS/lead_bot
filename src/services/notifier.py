"""Сервис уведомлений владельцу бизнеса."""

from aiogram import Bot

from src.config import settings
from src.database.models import Lead, LeadStatus, Meeting
from src.services.llm import generate_lead_summary
from src.utils.logger import logger


def _get_status_emoji_and_text(status: LeadStatus) -> tuple[str, str]:
    """Возвращает эмодзи и текст для статуса лида.

    Args:
        status: Статус лида

    Returns:
        Кортеж (эмодзи, текст статуса)
    """
    if status == LeadStatus.HOT:
        return "🔥", "ГОРЯЧИЙ"
    if status == LeadStatus.WARM:
        return "🟡", "ТЁПЛЫЙ"
    return "⚪️", "Новый"


def _get_fallback_summary_from_lead(lead: Lead) -> str:
    """Создаёт простое резюме из структурированных данных лида.

    Args:
        lead: Объект лида

    Returns:
        Простое резюме
    """
    summary_parts = []
    if lead.task:
        summary_parts.append(f"Задача: {lead.task}")
    if lead.budget:
        summary_parts.append(f"Бюджет: {lead.budget}")
    if lead.deadline:
        summary_parts.append(f"Срок: {lead.deadline}")
    return ". ".join(summary_parts) + "." if summary_parts else "Информация уточняется."


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
        emoji, status_text = _get_status_emoji_and_text(lead.status)

        # Имя лида
        lead_name: str = lead.first_name or lead.username or f"User {lead.telegram_id}"

        # Генерируем умное резюме через LLM
        try:
            summary = await generate_lead_summary(lead)
        except Exception as e:
            logger.error(f"Ошибка генерации резюме для лида {lead.id}: {e}")
            summary = _get_fallback_summary_from_lead(lead)

        # Формируем текст уведомления (используем HTML для надежности)
        notification: str = (
            f"{emoji} <b>Новый {status_text} лид!</b>\n\n"
            f"📝 <b>Резюме:</b> {summary}\n\n"
            f"👤 <b>Имя:</b> {lead_name}\n"
        )

        # Добавляем структурированные данные (если они есть)
        if lead.task:
            notification += f"📋 <b>Задача:</b> {lead.task}\n"

        if lead.budget:
            notification += f"💰 <b>Бюджет:</b> {lead.budget}\n"

        if lead.deadline:
            notification += f"⏰ <b>Срок:</b> {lead.deadline}\n"

        # Ссылка на пользователя
        if lead.username:
            notification += f"\n<b>Telegram:</b> @{lead.username}"
        else:
            notification += f"\n<b>Telegram ID:</b> <code>{lead.telegram_id}</code>"

        # Отправляем уведомление владельцу
        await bot.send_message(
            chat_id=settings.owner_telegram_id, text=notification, parse_mode="HTML"
        )

        logger.info(f"Уведомление о лиде {lead} отправлено владельцу")

    except Exception as e:
        logger.error(
            f"Ошибка при отправке уведомления владельцу о лиде {lead}: {e}",
            exc_info=True,
        )

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

        # Формируем текст уведомления (используем HTML для надежности)
        notification = (
            f"📅 <b>Новая встреча назначена!</b>\n\n"
            f"👤 <b>Имя</b>: {lead_name}\n"
            f"⏰ <b>Время</b>: {time_str}\n"
        )

        # Добавляем информацию о задаче, бюджете, сроке (если есть)
        if lead.task:
            notification += f"📋 <b>Задача</b>: {lead.task}\n"

        if lead.budget:
            notification += f"💰 <b>Бюджет</b>: {lead.budget}\n"

        if lead.deadline:
            notification += f"⏳ <b>Срок</b>: {lead.deadline}\n"

        # Ссылка на пользователя
        if lead.username:
            notification += f"\n<b>Telegram</b>: @{lead.username}"
        else:
            notification += f"\n<b>Telegram ID</b>: <code>{lead.telegram_id}</code>"

        # Отправляем уведомление владельцу
        await bot.send_message(
            chat_id=settings.owner_telegram_id, text=notification, parse_mode="HTML"
        )

        logger.info(f"Уведомление о встрече {meeting.id} для лида {lead.id} отправлено владельцу")

    except Exception as e:
        logger.error(
            f"Ошибка при отправке уведомления владельцу о встрече {meeting.id}: {e}",
            exc_info=True,
        )

    finally:
        await bot.session.close()
