"""Handler для назначения встреч с лидами."""

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.database.models import Lead, Meeting, MeetingStatus
from src.services.notifier import notify_owner_meeting_scheduled
from src.utils.logger import logger

router = Router(name="meetings")


def _format_date_ru(dt: datetime) -> str:
    """Форматирует дату по-русски (понедельник, 23 декабря)."""
    weekdays = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    months = [
        "",
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]
    weekday = weekdays[dt.weekday()]
    return f"{weekday}, {dt.day} {months[dt.month]}"


async def propose_meeting_times(lead: Lead, message: Message) -> None:
    """
    Предлагает лиду выбрать время встречи через inline keyboard.

    Args:
        lead: Объект лида из БД
        message: Сообщение от лида
    """
    # AICODE-NOTE: Для MVP используем локальное время (без timezone).
    # В продакшене добавить часовой пояс из настроек бизнеса.
    now = datetime.now()  # noqa: DTZ005

    # Генерируем слоты на ближайшие рабочие дни
    slots: list[tuple[datetime, str, str]] = []  # (datetime, label, callback_key)

    # Находим ближайшие 4 рабочих дня с утренними/дневными слотами
    current_date = now + timedelta(days=1)  # Начинаем с завтра
    slots_count = 0

    while slots_count < 4:
        # Пропускаем выходные (5=сб, 6=вс)
        if current_date.weekday() < 5:
            date_str = _format_date_ru(current_date)

            # Утренний слот 10:00
            morning = current_date.replace(hour=10, minute=0, second=0, microsecond=0)
            slots.append((morning, f"{date_str}, 10:00", f"slot_{slots_count}_am"))

            # Дневной слот 15:00
            afternoon = current_date.replace(hour=15, minute=0, second=0, microsecond=0)
            slots.append((afternoon, f"{date_str}, 15:00", f"slot_{slots_count}_pm"))

            slots_count += 1

        current_date += timedelta(days=1)

    # Сохраняем слоты в callback data (ограничение 64 байта — храним индекс)
    # AICODE-NOTE: Храним слоты во временной структуре через FSM было бы лучше,
    # но для MVP используем генерацию заново в callback handler

    buttons: list[list[InlineKeyboardButton]] = []

    # Показываем первые 4 слота (2 дня × 2 времени)
    for i, (_dt, label, _key) in enumerate(slots[:4]):
        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"meeting:{lead.id}:{i}",
                )
            ]
        )

    # Добавляем опцию "на следующей неделе" и "своё время"
    buttons.append(
        [
            InlineKeyboardButton(
                text="На следующей неделе",
                callback_data=f"meeting:{lead.id}:next_week",
            )
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                text="Предложить своё время",
                callback_data=f"meeting:{lead.id}:custom",
            )
        ]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer("Когда удобно созвониться?", reply_markup=keyboard)

    logger.info(f"Предложены варианты встреч для лида {lead.id}")


def _generate_meeting_slots() -> list[datetime]:
    """Генерирует список доступных слотов для встречи.

    Returns:
        Список datetime объектов (первые 4 рабочих дня, утро и день).
    """
    now = datetime.now()  # noqa: DTZ005
    slots: list[datetime] = []
    current_date = now + timedelta(days=1)  # Начинаем с завтра
    slots_count = 0

    while slots_count < 4:
        if current_date.weekday() < 5:  # Пропускаем выходные
            morning = current_date.replace(hour=10, minute=0, second=0, microsecond=0)
            afternoon = current_date.replace(hour=15, minute=0, second=0, microsecond=0)
            slots.extend([morning, afternoon])
            slots_count += 1
        current_date += timedelta(days=1)

    return slots


@router.callback_query(F.data.startswith("meeting:"))
async def handle_meeting_selection(callback: CallbackQuery) -> None:  # noqa: PLR0911, PLR0912
    """
    Обрабатывает выбор времени встречи лидом.

    Callback data format: "meeting:{lead_id}:{slot_index|next_week|custom}"
    """
    if not callback.data or not callback.message:
        return

    if not isinstance(callback.message, Message):
        await callback.answer()
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

    # Сразу убираем клавиатуру для защиты от повторных нажатий
    await callback.message.edit_reply_markup(reply_markup=None)

    # Определяем время встречи
    scheduled_at: datetime | None = None

    if slot == "custom":
        await callback.message.edit_text(
            "Напишите, когда вам удобно.\n\nНапример: «в среду в 11:00» или «28 декабря, 14:00»"
        )
        await callback.answer()
        logger.info(f"Лид {lead.id} выбрал своё время")
        return

    if slot == "next_week":
        # Находим понедельник следующей недели
        now = datetime.now()  # noqa: DTZ005
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = now + timedelta(days=days_until_monday)
        scheduled_at = next_monday.replace(hour=10, minute=0, second=0, microsecond=0)

    else:
        # Числовой индекс слота
        try:
            slot_index = int(slot)
            slots = _generate_meeting_slots()
            if 0 <= slot_index < len(slots):
                scheduled_at = slots[slot_index]
        except ValueError:
            pass

    if not scheduled_at:
        await callback.answer("Ошибка выбора времени", show_alert=True)
        return

    # Создаём встречу в БД
    meeting = await Meeting.create(
        lead=lead, scheduled_at=scheduled_at, status=MeetingStatus.SCHEDULED
    )

    # Форматируем время для отображения
    time_str = f"{_format_date_ru(scheduled_at)}, {scheduled_at.strftime('%H:%M')}"

    await callback.message.edit_text(
        f"Отлично! Звонок назначен: {time_str}.\n\n"
        f"Владелец свяжется с вами в Telegram.\n\n"
        f"Если что-то изменится — напишите."
    )

    await callback.answer()

    logger.info(f"Создана встреча {meeting.id} для лида {lead.id} на {scheduled_at}")

    # Уведомляем владельца о встрече
    try:
        await notify_owner_meeting_scheduled(lead, meeting)
    except Exception as e:
        logger.error(f"Ошибка при уведомлении владельца о встрече {meeting.id}: {e}")
