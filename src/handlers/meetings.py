"""Handler для назначения встреч с лидами."""

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.database.models import Lead, Meeting, MeetingStatus
from src.services.notifier import notify_owner_meeting_scheduled
from src.utils.logger import logger

router = Router(name="meetings")


async def propose_meeting_times(lead: Lead, message: Message) -> None:
    """
    Предлагает лиду выбрать время встречи через inline keyboard.

    Args:
        lead: Объект лида из БД
        message: Сообщение от лида
    """
    # AICODE-NOTE: Для MVP используем фиксированные варианты времени
    # В будущем можно добавить интеграцию с Google Calendar для проверки свободных слотов

    # Генерируем варианты времени
    # AICODE-NOTE: Используем локальное время для MVP (без timezone)
    now = datetime.now()  # noqa: DTZ005
    today_18 = now.replace(hour=18, minute=0, second=0, microsecond=0)
    tomorrow_10 = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    tomorrow_14 = (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)

    # Создаём inline keyboard с вариантами
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📅 Сегодня в {today_18.strftime('%H:%M')}",
                    callback_data=f"meeting:{lead.id}:today_18",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"📅 Завтра в {tomorrow_10.strftime('%H:%M')}",
                    callback_data=f"meeting:{lead.id}:tomorrow_10",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"📅 Завтра в {tomorrow_14.strftime('%H:%M')}",
                    callback_data=f"meeting:{lead.id}:tomorrow_14",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✍️ Предложить своё время", callback_data=f"meeting:{lead.id}:custom"
                )
            ],
        ]
    )

    await message.answer(
        "Отлично! 🎉\n\nДавайте назначим встречу. Когда вам будет удобно?", reply_markup=keyboard
    )

    logger.info(f"Предложены варианты встреч для лида {lead.id}")


@router.callback_query(F.data.startswith("meeting:"))
async def handle_meeting_selection(callback: CallbackQuery) -> None:
    """
    Обрабатывает выбор времени встречи лидом.

    Callback data format: "meeting:{lead_id}:{slot}"
    где slot: today_18, tomorrow_10, tomorrow_14, custom
    """
    if not callback.data or not callback.message:
        return

    # Парсим callback data
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка формата данных", show_alert=True)
        return

    _, lead_id_str, slot = parts

    try:
        lead_id = int(lead_id_str)
    except ValueError:
        await callback.answer("Ошибка: некорректный ID лида", show_alert=True)
        return

    # Загружаем лида из БД
    lead = await Lead.get_or_none(id=lead_id)
    if not lead:
        await callback.answer("Ошибка: лид не найден", show_alert=True)
        return

    # Определяем время встречи
    now = datetime.now()  # noqa: DTZ005
    scheduled_at: datetime | None = None

    if slot == "today_18":
        scheduled_at = now.replace(hour=18, minute=0, second=0, microsecond=0)
    elif slot == "tomorrow_10":
        scheduled_at = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    elif slot == "tomorrow_14":
        scheduled_at = (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    elif slot == "custom":
        # AICODE-NOTE: Для MVP просто просим написать время текстом
        # В будущем можно добавить calendar picker или text state handler
        await callback.message.edit_text(
            "Напишите, пожалуйста, когда вам удобно встретиться.\n\n"
            "Например: 'завтра в 15:00' или '25 декабря в 10:00'"
        )
        await callback.answer()
        logger.info(f"Лид {lead.id} выбрал custom время")
        return

    if not scheduled_at:
        await callback.answer("Ошибка выбора времени", show_alert=True)
        return

    # Создаём встречу в БД
    meeting = await Meeting.create(
        lead=lead, scheduled_at=scheduled_at, status=MeetingStatus.SCHEDULED
    )

    # Форматируем время для отображения
    time_str = scheduled_at.strftime("%d.%m.%Y в %H:%M")

    # Обновляем сообщение (убираем клавиатуру)
    await callback.message.edit_text(
        f"✅ Отлично! Встреча назначена на **{time_str}**.\n\n"
        f"Владелец бизнеса свяжется с вами в Telegram ближе к назначенному времени.\n\n"
        f"Если возникнут вопросы — пишите!",
        parse_mode="Markdown",
    )

    await callback.answer("Встреча назначена! ✅")

    logger.info(f"Создана встреча {meeting.id} для лида {lead.id} на {scheduled_at}")

    # Уведомляем владельца о встрече
    try:
        await notify_owner_meeting_scheduled(lead, meeting)
    except Exception as e:
        # AICODE-NOTE: Не критичная ошибка, встреча уже создана
        logger.error(f"Ошибка при уведомлении владельца о встрече {meeting.id}: {e}")
