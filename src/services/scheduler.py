"""Планировщик фоновых задач для follow-up и напоминаний."""

import asyncio
from datetime import UTC, datetime, timedelta

from aiogram import Bot

from src.database.models import Lead, LeadStatus
from src.utils.logger import logger


async def send_follow_up(bot: Bot, lead: Lead) -> None:
    """
    Отправляет follow-up сообщение лиду.

    Args:
        bot: Aiogram Bot instance
        lead: Объект лида
    """
    # Определяем текст сообщения в зависимости от количества попыток
    if lead.follow_up_count == 0:
        message = (
            "Привет! 👋\n\n"
            "Заметил, что вы не ответили. Всё ещё актуален ваш вопрос?\n\n"
            "Если да — напишите, помогу!"
        )
    else:
        message = (
            "Здравствуйте! 👋\n\n"
            "Напоминаю о себе. Если вопрос актуален — пишите, буду рад помочь!\n\n"
            "Если сейчас не до этого — ничего страшного, обращайтесь когда будет удобно."
        )

    try:
        await bot.send_message(chat_id=lead.telegram_id, text=message)
        logger.info(f"Отправлен follow-up лиду {lead.id} (попытка {lead.follow_up_count + 1})")
    except Exception as e:
        logger.error(f"Ошибка отправки follow-up лиду {lead.id}: {e}")


async def check_follow_ups(bot: Bot) -> None:
    """
    Проверяет лидов для follow-up (запускается каждый час).

    Логика:
    - Если лид не отвечал 24 часа → отправить 1-й follow-up
    - Если лид не отвечал 48 часов → отправить 2-й follow-up
    - После 2-х follow-up → перевести в COLD
    """
    now = datetime.now(tz=UTC)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_48h = now - timedelta(hours=48)

    # AICODE-NOTE: Ищем лидов, которые не отвечали 24+ часов и ещё не получили 2 follow-up
    leads_for_first_followup = await Lead.filter(
        last_message_at__lt=cutoff_24h,
        status__in=[LeadStatus.NEW, LeadStatus.WARM],
        follow_up_count=0,
    ).all()

    for lead in leads_for_first_followup:
        await send_follow_up(bot, lead)
        lead.follow_up_count += 1
        await lead.save()

    # Ищем лидов для второго follow-up (48+ часов, 1 follow-up уже был)
    leads_for_second_followup = await Lead.filter(
        last_message_at__lt=cutoff_48h,
        status__in=[LeadStatus.NEW, LeadStatus.WARM],
        follow_up_count=1,
    ).all()

    for lead in leads_for_second_followup:
        await send_follow_up(bot, lead)
        lead.follow_up_count += 1
        await lead.save()

    # Переводим в COLD тех, кто не ответил после 2-х follow-up
    leads_to_cold = await Lead.filter(
        last_message_at__lt=cutoff_48h,
        status__in=[LeadStatus.NEW, LeadStatus.WARM],
        follow_up_count__gte=2,
    ).all()

    for lead in leads_to_cold:
        lead.status = LeadStatus.COLD
        await lead.save()
        logger.info(f"Лид {lead.id} переведён в COLD после 2-х follow-up без ответа")

    logger.info(
        f"Follow-up проверка завершена: "
        f"{len(leads_for_first_followup)} первых, "
        f"{len(leads_for_second_followup)} вторых, "
        f"{len(leads_to_cold)} переведено в COLD"
    )


async def run_scheduler(bot: Bot) -> None:
    """
    Запускает планировщик фоновых задач.

    Проверяет follow-up каждый час.

    Args:
        bot: Aiogram Bot instance
    """
    logger.info("Планировщик follow-up запущен")

    while True:
        try:
            await check_follow_ups(bot)
        except Exception as e:
            logger.error(f"Ошибка в планировщике follow-up: {e}", exc_info=True)

        # Ждём 1 час до следующей проверки
        await asyncio.sleep(3600)  # 3600 секунд = 1 час
