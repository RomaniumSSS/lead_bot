"""Модуль для создания inline клавиатур структурированного диалога."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.database.models import LeadStatus


def get_task_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора задачи (этап TASK)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Создание сайта", callback_data="task:website")],
            [InlineKeyboardButton(text="🎨 Дизайн", callback_data="task:design")],
            [InlineKeyboardButton(text="💻 Разработка приложения", callback_data="task:app")],
            [InlineKeyboardButton(text="✍️ Своя задача", callback_data="task:custom")],
        ]
    )


def get_budget_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора бюджета (этап BUDGET)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 До 50 000 ₽", callback_data="budget:low")],
            [InlineKeyboardButton(text="💰 50 000 - 150 000 ₽", callback_data="budget:medium")],
            [InlineKeyboardButton(text="💰 150 000+ ₽", callback_data="budget:high")],
            [InlineKeyboardButton(text="🤷 Пока не знаю", callback_data="budget:unknown")],
        ]
    )


def get_deadline_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора срока (этап DEADLINE)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔥 Срочно (на этой неделе)", callback_data="deadline:urgent"
                )
            ],
            [InlineKeyboardButton(text="⏰ Скоро (в этом месяце)", callback_data="deadline:soon")],
            [
                InlineKeyboardButton(
                    text="📅 Не срочно (есть время)", callback_data="deadline:later"
                )
            ],
        ]
    )


def get_action_keyboard(status: LeadStatus) -> InlineKeyboardMarkup:
    """Клавиатура действий после квалификации (этап ACTION).

    Args:
        status: Статус лида для определения доступных кнопок.

    Returns:
        InlineKeyboardMarkup с кнопками действий.
    """
    buttons: list[list[InlineKeyboardButton]] = []

    # Только горячим лидам активно предлагаем встречу
    if status == LeadStatus.HOT:
        buttons.append(
            [InlineKeyboardButton(text="Назначить звонок", callback_data="action:schedule_meeting")]
        )

    # Всем предлагаем материалы
    buttons.append(
        [InlineKeyboardButton(text="Получить материалы", callback_data="action:send_materials")]
    )

    # Кнопка для перехода в свободный диалог
    buttons.append([InlineKeyboardButton(text="Задать вопрос", callback_data="action:free_chat")])

    # Тёплым лидам показываем встречу, но ниже — не навязываем
    if status == LeadStatus.WARM:
        buttons.append(
            [InlineKeyboardButton(text="Обсудить лично", callback_data="action:schedule_meeting")]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_free_chat_keyboard(show_meeting: bool = True) -> InlineKeyboardMarkup:
    """Клавиатура для свободного диалога (этап FREE_CHAT).

    Args:
        show_meeting: Показывать ли кнопку встречи (False для холодных лидов).
    """
    buttons: list[list[InlineKeyboardButton]] = []

    if show_meeting:
        buttons.append(
            [InlineKeyboardButton(text="Назначить звонок", callback_data="action:schedule_meeting")]
        )

    buttons.extend(
        [
            [
                InlineKeyboardButton(
                    text="Получить материалы", callback_data="action:send_materials"
                )
            ],
            [InlineKeyboardButton(text="Начать заново", callback_data="action:restart")],
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Маппинг task callback → читаемое название задачи
TASK_LABELS: dict[str, str] = {
    "website": "Создание сайта",
    "design": "Дизайн",
    "app": "Разработка приложения",
}

# Маппинг budget callback → читаемое название и коэффициент для квалификации
BUDGET_LABELS: dict[str, str] = {
    "low": "До 50 000 ₽",
    "medium": "50 000 - 150 000 ₽",
    "high": "150 000+ ₽",
    "unknown": "Пока не знаю",
}

# Маппинг deadline callback → читаемое название
DEADLINE_LABELS: dict[str, str] = {
    "urgent": "Срочно (на этой неделе)",
    "soon": "Скоро (в этом месяце)",
    "later": "Не срочно (есть время)",
}


def get_suggested_questions_keyboard(questions: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура с предложенными вопросами от LLM.

    Args:
        questions: Список предложенных вопросов (3-4 штуки)

    Returns:
        InlineKeyboardMarkup с кнопками вопросов + кнопка "Свой вопрос"
    """
    buttons: list[list[InlineKeyboardButton]] = []

    # Эмодзи для вопросов
    emojis = ["📋", "💰", "🎨", "⏰"]

    # Добавляем кнопки с вопросами
    for idx, question in enumerate(questions):
        emoji = emojis[idx % len(emojis)]
        # Обрезаем вопрос до 60 символов для кнопки
        button_text = f"{emoji} {question[:60]}"
        # Сохраняем индекс вопроса в callback_data
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"question:{idx}")])

    # Добавляем кнопку "Свой вопрос"
    buttons.append([InlineKeyboardButton(text="✍️ Свой вопрос", callback_data="question:custom")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_progress_indicator(current_state: str) -> str:
    """Возвращает минималистичный индикатор прогресса.

    Args:
        current_state: Текущий state (например, "ConversationState:BUDGET").

    Returns:
        Строка с визуальным индикатором прогресса.
    """
    # Извлекаем имя state из полного пути
    state_name = current_state.split(":")[-1] if current_state else ""

    states = ["TASK", "BUDGET", "DEADLINE", "ACTION"]
    labels = {
        "TASK": "Задача",
        "BUDGET": "Бюджет",
        "DEADLINE": "Сроки",
        "ACTION": "Итог",
    }

    current_idx = states.index(state_name) if state_name in states else 0
    current_step = current_idx + 1
    total_steps = len(states)

    return f"Шаг {current_step} из {total_steps}: {labels.get(state_name, 'Задача')}"


__all__ = [
    "BUDGET_LABELS",
    "DEADLINE_LABELS",
    "TASK_LABELS",
    "get_action_keyboard",
    "get_budget_keyboard",
    "get_deadline_keyboard",
    "get_free_chat_keyboard",
    "get_progress_indicator",
    "get_suggested_questions_keyboard",
    "get_task_keyboard",
]
