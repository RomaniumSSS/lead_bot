"""Тесты для inline клавиатур.

Эти тесты важны — если забыть callback_data или ошибиться
в структуре, бот упадёт в runtime когда клиент нажмёт кнопку.
"""

from aiogram.types import InlineKeyboardMarkup

from src.database.models import LeadStatus
from src.keyboards import (
    get_action_keyboard,
    get_budget_keyboard,
    get_deadline_keyboard,
    get_free_chat_keyboard,
    get_progress_indicator,
    get_suggested_questions_keyboard,
    get_task_keyboard,
)


class TestTaskKeyboard:
    """Тесты клавиатуры выбора задачи."""

    def test_returns_valid_keyboard(self) -> None:
        """Возвращает InlineKeyboardMarkup."""
        kb = get_task_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_4_task_options(self) -> None:
        """Содержит 4 варианта задачи."""
        kb = get_task_keyboard()
        assert len(kb.inline_keyboard) == 4

    def test_all_buttons_have_callback_data(self) -> None:
        """Все кнопки имеют callback_data."""
        kb = get_task_keyboard()
        for row in kb.inline_keyboard:
            for button in row:
                assert button.callback_data is not None
                assert button.callback_data.startswith("task:")

    def test_custom_task_option_exists(self) -> None:
        """Есть опция 'Своя задача'."""
        kb = get_task_keyboard()
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "task:custom" in callbacks


class TestBudgetKeyboard:
    """Тесты клавиатуры выбора бюджета."""

    def test_returns_valid_keyboard(self) -> None:
        """Возвращает InlineKeyboardMarkup."""
        kb = get_budget_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_5_budget_options(self) -> None:
        """Содержит 5 вариантов бюджета (включая 'Свой вариант')."""
        kb = get_budget_keyboard()
        assert len(kb.inline_keyboard) == 5

    def test_all_buttons_have_callback_data(self) -> None:
        """Все кнопки имеют callback_data."""
        kb = get_budget_keyboard()
        for row in kb.inline_keyboard:
            for button in row:
                assert button.callback_data is not None
                assert button.callback_data.startswith("budget:")


class TestDeadlineKeyboard:
    """Тесты клавиатуры выбора срока."""

    def test_returns_valid_keyboard(self) -> None:
        """Возвращает InlineKeyboardMarkup."""
        kb = get_deadline_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_4_deadline_options(self) -> None:
        """Содержит 4 варианта срока (включая 'Свой вариант')."""
        kb = get_deadline_keyboard()
        assert len(kb.inline_keyboard) == 4


class TestActionKeyboard:
    """Тесты клавиатуры действий после квалификации."""

    def test_hot_lead_has_meeting_button(self) -> None:
        """HOT лид видит кнопку встречи первой."""
        kb = get_action_keyboard(LeadStatus.HOT)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "action:schedule_meeting" in callbacks
        # Встреча должна быть первой кнопкой
        assert callbacks[0] == "action:schedule_meeting"

    def test_warm_lead_has_meeting_button_lower(self) -> None:
        """WARM лид видит кнопку встречи, но не первой."""
        kb = get_action_keyboard(LeadStatus.WARM)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "action:schedule_meeting" in callbacks
        # Встреча НЕ первая (сначала материалы)
        assert callbacks[0] != "action:schedule_meeting"

    def test_cold_lead_no_meeting_button(self) -> None:
        """COLD лид НЕ видит кнопку встречи."""
        kb = get_action_keyboard(LeadStatus.COLD)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "action:schedule_meeting" not in callbacks

    def test_all_leads_have_materials_button(self) -> None:
        """Все лиды видят кнопку материалов."""
        for status in [LeadStatus.HOT, LeadStatus.WARM, LeadStatus.COLD]:
            kb = get_action_keyboard(status)
            callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
            assert "action:send_materials" in callbacks

    def test_all_leads_have_question_button(self) -> None:
        """Все лиды видят кнопку вопроса."""
        for status in [LeadStatus.HOT, LeadStatus.WARM, LeadStatus.COLD]:
            kb = get_action_keyboard(status)
            callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
            assert "action:free_chat" in callbacks


class TestFreeChatKeyboard:
    """Тесты клавиатуры свободного диалога."""

    def test_with_meeting_shows_meeting_button(self) -> None:
        """С show_meeting=True показывает кнопку встречи."""
        kb = get_free_chat_keyboard(show_meeting=True)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "action:schedule_meeting" in callbacks

    def test_without_meeting_hides_meeting_button(self) -> None:
        """С show_meeting=False НЕ показывает кнопку встречи."""
        kb = get_free_chat_keyboard(show_meeting=False)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "action:schedule_meeting" not in callbacks

    def test_always_has_restart_button(self) -> None:
        """Всегда есть кнопка 'Начать заново'."""
        kb = get_free_chat_keyboard(show_meeting=False)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "action:restart" in callbacks


class TestSuggestedQuestionsKeyboard:
    """Тесты клавиатуры предложенных вопросов."""

    def test_creates_buttons_for_questions(self) -> None:
        """Создаёт кнопки для переданных вопросов."""
        questions = ["Вопрос 1?", "Вопрос 2?", "Вопрос 3?"]
        kb = get_suggested_questions_keyboard(questions)

        # 3 вопроса + 1 "Свой вопрос"
        assert len(kb.inline_keyboard) == 4

    def test_custom_question_button_exists(self) -> None:
        """Есть кнопка 'Свой вопрос'."""
        questions = ["Вопрос 1?"]
        kb = get_suggested_questions_keyboard(questions)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

        assert "question:custom" in callbacks

    def test_question_buttons_have_indices(self) -> None:
        """Кнопки вопросов имеют индексы в callback_data."""
        questions = ["Вопрос 1?", "Вопрос 2?"]
        kb = get_suggested_questions_keyboard(questions)

        # Первая кнопка = question:0, вторая = question:1
        assert kb.inline_keyboard[0][0].callback_data == "question:0"
        assert kb.inline_keyboard[1][0].callback_data == "question:1"

    def test_long_question_is_truncated(self) -> None:
        """Длинный вопрос обрезается до 60 символов."""
        long_question = (
            "Это очень длинный вопрос который должен быть обрезан потому что он слишком длинный"
        )
        kb = get_suggested_questions_keyboard([long_question])

        button_text = kb.inline_keyboard[0][0].text
        # Эмодзи (2 символа) + пробел + 60 символов текста
        assert len(button_text) <= 64


class TestProgressIndicator:
    """Тесты индикатора прогресса."""

    def test_task_is_step_1(self) -> None:
        """TASK = шаг 1."""
        result = get_progress_indicator("TASK")
        assert "1 из 4" in result
        assert "Задача" in result

    def test_budget_is_step_2(self) -> None:
        """BUDGET = шаг 2."""
        result = get_progress_indicator("BUDGET")
        assert "2 из 4" in result
        assert "Бюджет" in result

    def test_deadline_is_step_3(self) -> None:
        """DEADLINE = шаг 3."""
        result = get_progress_indicator("DEADLINE")
        assert "3 из 4" in result
        assert "Сроки" in result

    def test_action_is_step_4(self) -> None:
        """ACTION = шаг 4."""
        result = get_progress_indicator("ACTION")
        assert "4 из 4" in result
        assert "Итог" in result

    def test_unknown_state_defaults_to_task(self) -> None:
        """Неизвестный state → показываем шаг 1."""
        result = get_progress_indicator("UNKNOWN")
        assert "1 из 4" in result
