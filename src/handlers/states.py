"""FSM States для структурированного диалога с лидами."""

from aiogram.fsm.state import State, StatesGroup


class ConversationState(StatesGroup):
    """Состояния диалога с лидом.

    Поток: TASK → BUDGET → DEADLINE → ACTION → FREE_CHAT
    """

    # Этап 1: Выяснение задачи
    TASK = State()

    # Этап 2: Выяснение бюджета
    BUDGET = State()

    # Этап 3: Выяснение срока
    DEADLINE = State()

    # Этап 4: Действие (встреча/материалы) - квалификация завершена
    ACTION = State()

    # Этап 5: Свободный диалог после квалификации
    FREE_CHAT = State()

    # Дополнительные states: ожидание пользовательского ввода
    TASK_CUSTOM_INPUT = State()  # Ожидание ввода своей задачи
    BUDGET_CUSTOM_INPUT = State()  # Ожидание ввода своего бюджета
    DEADLINE_CUSTOM_INPUT = State()  # Ожидание ввода своего срока
    MEETING_CUSTOM_TIME = State()  # Ожидание ввода своего времени встречи
