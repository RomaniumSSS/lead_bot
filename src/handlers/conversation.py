"""Handler для структурированного диалога с лидами через FSM."""

from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.config import settings
from src.database.models import Conversation, Lead, LeadStatus, MessageRole
from src.handlers.states import ConversationState
from src.keyboards import (
    BUDGET_LABELS,
    DEADLINE_LABELS,
    TASK_LABELS,
    get_action_keyboard,
    get_budget_keyboard,
    get_deadline_keyboard,
    get_free_chat_keyboard,
    get_meeting_suggestion_keyboard,
    get_progress_indicator,
    get_suggested_questions_keyboard,
    get_task_keyboard,
)
from src.services.llm import generate_response_free_chat, generate_suggested_questions
from src.services.notifier import notify_owner_about_lead
from src.types import LLMResponse
from src.utils.logger import logger

router = Router(name="conversation")


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================


async def _update_last_message_time(lead: Lead) -> None:
    """
    Обновляет время последнего сообщения от лида и сбрасывает счётчик follow-up.

    Args:
        lead: Объект лида
    """
    lead.last_message_at = datetime.now(tz=UTC)
    lead.follow_up_count = 0  # Сбрасываем счётчик, т.к. лид ответил
    await lead.save()


# =============================================================================
# ЗАЩИТА КНОПОК ОТ ПОВТОРНОГО НАЖАТИЯ
# =============================================================================


async def _check_state_and_answer(
    callback: CallbackQuery, state: FSMContext, expected_state: str
) -> bool:
    """Проверяет текущий state и отвечает на callback если state неверный.

    Args:
        callback: Объект callback query
        state: FSM context
        expected_state: Ожидаемый state (например, "TASK")

    Returns:
        True если state корректный, False если кнопка уже не актуальна.
    """
    current_state = await state.get_state()

    # Если state не установлен или не соответствует ожидаемому — кнопка устарела
    if not current_state or expected_state not in current_state:
        await callback.answer("Эта кнопка уже не актуальна", show_alert=False)
        return False

    return True


# =============================================================================
# CALLBACK HANDLERS для кнопок
# =============================================================================


@router.callback_query(F.data.startswith("task:"))
async def handle_task_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка выбора задачи через кнопку."""
    if not callback.data or not callback.message or not callback.from_user:
        return

    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    # Защита от повторного нажатия
    if not await _check_state_and_answer(callback, state, "TASK"):
        return

    task_type = callback.data.split(":")[1]

    # Сразу убираем клавиатуру чтобы предотвратить повторные нажатия
    await callback.message.edit_reply_markup(reply_markup=None)

    # Если выбрана "Своя задача" — просим ввести текстом
    if task_type == "custom":
        progress = get_progress_indicator("TASK")
        await callback.message.answer(f"{progress}\n\nОпишите вашу задачу:")
        await state.set_state(ConversationState.TASK_CUSTOM_INPUT)
        await callback.answer()
        return

    # Получаем читаемое название задачи
    task = TASK_LABELS.get(task_type, "Не указано")

    # Сохраняем в FSM context
    await state.update_data(task=task)

    # Получаем лида и сохраняем в БД
    lead = await Lead.get_or_none(telegram_id=callback.from_user.id)
    if lead:
        lead.task = task
        await _update_last_message_time(lead)

        await Conversation.create(
            lead=lead,
            role=MessageRole.USER,
            content=f"[Выбрана задача: {task}]",
        )

    # Отправляем подтверждение и следующий вопрос
    progress = get_progress_indicator("BUDGET")
    await callback.message.answer(
        f"Задача: {task}\n\n{progress}\n\nКакой примерный бюджет?",
        reply_markup=get_budget_keyboard(),
    )

    await state.set_state(ConversationState.BUDGET)
    await callback.answer()

    logger.info(f"Лид {lead.id if lead else '?'} выбрал задачу: {task}")


@router.callback_query(F.data.startswith("budget:"))
async def handle_budget_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка выбора бюджета через кнопку."""
    if not callback.data or not callback.message or not callback.from_user:
        return

    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    # Защита от повторного нажатия
    if not await _check_state_and_answer(callback, state, "BUDGET"):
        return

    # Сразу убираем клавиатуру
    await callback.message.edit_reply_markup(reply_markup=None)

    budget_type = callback.data.split(":")[1]

    # Если выбран "Свой вариант" — просим ввести текстом
    if budget_type == "custom":
        progress = get_progress_indicator("BUDGET")
        await callback.message.answer(f"{progress}\n\nНапишите ваш примерный бюджет:")
        await state.set_state(ConversationState.BUDGET_CUSTOM_INPUT)
        await callback.answer()
        return

    budget = BUDGET_LABELS.get(budget_type, "Не указан")

    # Сохраняем в FSM context
    await state.update_data(budget=budget)

    # Получаем лида и сохраняем в БД
    lead = await Lead.get_or_none(telegram_id=callback.from_user.id)
    if lead:
        lead.budget = budget
        await _update_last_message_time(lead)

        await Conversation.create(
            lead=lead,
            role=MessageRole.USER,
            content=f"[Выбран бюджет: {budget}]",
        )

    # Получаем данные для показа
    fsm_data = await state.get_data()
    task = fsm_data.get("task", "—")

    # Отправляем подтверждение и следующий вопрос
    progress = get_progress_indicator("DEADLINE")
    await callback.message.answer(
        f"Задача: {task}\nБюджет: {budget}\n\n{progress}\n\nКогда нужен результат?",
        reply_markup=get_deadline_keyboard(),
    )

    await state.set_state(ConversationState.DEADLINE)
    await callback.answer()

    logger.info(f"Лид {lead.id if lead else '?'} выбрал бюджет: {budget}")


@router.callback_query(F.data.startswith("deadline:"))
async def handle_deadline_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка выбора срока через кнопку. Выполняет квалификацию."""
    if not callback.data or not callback.message or not callback.from_user:
        return

    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    # Защита от повторного нажатия
    if not await _check_state_and_answer(callback, state, "DEADLINE"):
        return

    # Сразу убираем клавиатуру
    await callback.message.edit_reply_markup(reply_markup=None)

    deadline_type = callback.data.split(":")[1]

    # Если выбран "Свой вариант" — просим ввести текстом
    if deadline_type == "custom":
        progress = get_progress_indicator("DEADLINE")
        await callback.message.answer(f"{progress}\n\nНапишите, когда вам нужен результат:")
        await state.set_state(ConversationState.DEADLINE_CUSTOM_INPUT)
        await callback.answer()
        return

    deadline = DEADLINE_LABELS.get(deadline_type, "Не указан")

    # Сохраняем в FSM context
    await state.update_data(deadline=deadline)

    # Получаем лида
    lead = await Lead.get_or_none(telegram_id=callback.from_user.id)
    if not lead:
        await callback.answer("Ошибка: лид не найден", show_alert=True)
        return

    # Сохраняем срок в БД
    lead.deadline = deadline
    await _update_last_message_time(lead)

    await Conversation.create(
        lead=lead,
        role=MessageRole.USER,
        content=f"[Выбран срок: {deadline}]",
    )

    # Получаем все данные для квалификации
    fsm_data = await state.get_data()
    task = fsm_data.get("task", "—")
    budget = fsm_data.get("budget", "—")

    # Выполняем квалификацию на основе выбранных параметров
    new_status = _qualify_lead(deadline_type, budget)
    old_status = lead.status
    lead.status = new_status
    await lead.save()

    # Определяем, нужно ли уведомлять владельца
    # Уведомляем только при ПОВЫШЕНИИ статуса (NEW→WARM, NEW→HOT, WARM→HOT)
    status_priority = {LeadStatus.NEW: 0, LeadStatus.COLD: 1, LeadStatus.WARM: 2, LeadStatus.HOT: 3}
    status_upgraded = status_priority.get(new_status, 0) > status_priority.get(old_status, 0)

    logger.info(
        f"Лид {lead.id} квалифицирован: {old_status.value} → {new_status.value} "
        f"(notify={status_upgraded})"
    )

    # Формируем сообщение на основе статуса — коротко и по делу
    summary = f"Задача: {task}\nБюджет: {budget}\nСроки: {deadline}\n\n"

    if new_status == LeadStatus.HOT:
        message_text = (
            summary + "Отлично, проект срочный!\n\n"
            f"Предлагаю назначить звонок с {settings.business_name} — обсудим детали."
        )
    elif new_status == LeadStatus.WARM:
        message_text = (
            summary + "Понял, спасибо за информацию.\n\n"
            "Могу отправить примеры наших работ или ответить на вопросы."
        )
    else:  # COLD
        message_text = (
            summary + "Спасибо за интерес!\n\n"
            "Могу отправить материалы для ознакомления или ответить на вопросы."
        )

    await callback.message.answer(message_text, reply_markup=get_action_keyboard(new_status))

    await state.set_state(ConversationState.ACTION)
    await callback.answer()

    # Сохраняем флаг для отложенного уведомления (если лид назначит встречу — уведомим там)
    # AICODE-NOTE: Уведомление о лиде отправляется позже, чтобы не спамить двумя сообщениями
    if status_upgraded and new_status in [LeadStatus.HOT, LeadStatus.WARM]:
        await state.update_data(pending_lead_notification=True)
        logger.info(f"Отложено уведомление о лиде {lead.id} (pending_lead_notification=True)")


@router.callback_query(F.data.startswith("question:"))
async def handle_question_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка выбора предложенного вопроса."""
    if not callback.data or not callback.message or not callback.from_user:
        return

    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    # Сразу убираем клавиатуру
    await callback.message.edit_reply_markup(reply_markup=None)

    question_action = callback.data.split(":")[1]

    # Если выбран "Свой вопрос" — ждём текстового ввода
    if question_action == "custom":
        lead = await Lead.get_or_none(telegram_id=callback.from_user.id)
        show_meeting = lead.status != LeadStatus.COLD if lead else True

        await callback.message.answer(
            "Напишите ваш вопрос:", reply_markup=get_free_chat_keyboard(show_meeting=show_meeting)
        )
        await callback.answer()
        return

    # Иначе — получаем выбранный вопрос из FSM
    fsm_data = await state.get_data()
    suggested_questions: list[str] = fsm_data.get("suggested_questions", [])

    try:
        question_idx = int(question_action)
        if question_idx < 0 or question_idx >= len(suggested_questions):
            await callback.answer("Ошибка: вопрос не найден", show_alert=True)
            return

        selected_question = suggested_questions[question_idx]

        # Сохраняем выбранный вопрос как сообщение от пользователя
        lead = await Lead.get_or_none(telegram_id=callback.from_user.id)
        if not lead:
            await callback.answer("Ошибка: лид не найден", show_alert=True)
            return

        await _update_last_message_time(lead)

        # Сохраняем вопрос в историю
        await Conversation.create(
            lead=lead,
            role=MessageRole.USER,
            content=selected_question,
        )

        # Генерируем ответ через LLM
        show_meeting = lead.status != LeadStatus.COLD

        try:
            response_data: LLMResponse = await generate_response_free_chat(lead, selected_question)
            bot_response = response_data["response"]

            # Сохраняем ответ бота
            await Conversation.create(
                lead=lead,
                role=MessageRole.ASSISTANT,
                content=bot_response,
            )

            await callback.message.answer(
                f"❓ {selected_question}\n\n{bot_response}",
                reply_markup=get_free_chat_keyboard(show_meeting=show_meeting),
            )

            await callback.answer()
            logger.info(f"Лид {lead.id} выбрал вопрос: {selected_question}")

        except Exception as e:
            logger.error(f"Ошибка LLM для лида {lead.id}: {e}", exc_info=True)
            await callback.message.answer(
                "Извините, произошла ошибка. Попробуйте переформулировать вопрос.",
                reply_markup=get_free_chat_keyboard(show_meeting=show_meeting),
            )
            await callback.answer()

    except (ValueError, IndexError):
        await callback.answer("Ошибка: неверный формат вопроса", show_alert=True)


async def _send_pending_lead_notification(lead: Lead, state: FSMContext) -> None:
    """Отправляет отложенное уведомление о лиде, если оно есть.

    Args:
        lead: Объект лида
        state: FSM context для проверки флага
    """
    fsm_data = await state.get_data()
    if fsm_data.get("pending_lead_notification"):
        try:
            await notify_owner_about_lead(lead)
            await state.update_data(pending_lead_notification=False)
        except Exception as e:
            logger.error(f"Ошибка отправки отложенного уведомления о лиде {lead.id}: {e}")


@router.callback_query(F.data.startswith("action:"))
async def handle_action_callback(callback: CallbackQuery, state: FSMContext) -> None:  # noqa: PLR0912
    """Обработка кнопок действий после квалификации."""
    if not callback.data or not callback.message or not callback.from_user:
        return

    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    action = callback.data.split(":")[1]
    lead = await Lead.get_or_none(telegram_id=callback.from_user.id)

    # Сразу убираем клавиатуру для всех действий
    await callback.message.edit_reply_markup(reply_markup=None)

    # Определяем, показывать ли кнопку встречи (не для холодных)
    show_meeting = lead.status != LeadStatus.COLD if lead else True

    if action == "schedule_meeting":
        # AICODE-NOTE: Здесь НЕ отправляем pending уведомление — оно отправится
        # в meetings.py вместе с уведомлением о встрече (объединённое)
        # Защита: холодным лидам не даём назначать встречу
        if lead and lead.status == LeadStatus.COLD:
            await callback.message.answer(
                "Сейчас мы можем прислать материалы для ознакомления.\n"
                "Когда будете готовы обсудить детали — напишите!",
                reply_markup=get_free_chat_keyboard(show_meeting=False),
            )
            await state.set_state(ConversationState.FREE_CHAT)
            await callback.answer()
            return

        # AICODE-NOTE: Динамический импорт для избежания циклических зависимостей
        from src.handlers.meetings import propose_meeting_times

        if lead:
            await propose_meeting_times(lead, callback.message)
        await callback.answer()

    elif action == "send_materials":
        await _send_materials(callback.message, lead)
        await callback.answer()

        # Отправляем отложенное уведомление о лиде (если есть)
        if lead:
            await _send_pending_lead_notification(lead, state)

        # Переход в свободный диалог
        await callback.message.answer(
            "Если есть вопросы — пишите, отвечу.",
            reply_markup=get_free_chat_keyboard(show_meeting=show_meeting),
        )
        await state.set_state(ConversationState.FREE_CHAT)

    elif action == "free_chat":
        # Отправляем отложенное уведомление о лиде (если есть)
        if lead:
            await _send_pending_lead_notification(lead, state)
        # Генерируем предложенные вопросы через LLM
        if lead:
            try:
                # Генерируем вопросы
                suggested_questions = await generate_suggested_questions(lead)

                # Сохраняем в FSM для обработки выбора
                await state.update_data(suggested_questions=suggested_questions)

                # Показываем вопросы (без лишнего промежуточного сообщения)
                await callback.message.answer(
                    "Что вас интересует?",
                    reply_markup=get_suggested_questions_keyboard(suggested_questions),
                )

                await state.set_state(ConversationState.FREE_CHAT)
                await callback.answer()
                logger.info(f"Предложены вопросы для лида {lead.id}: {suggested_questions}")

            except Exception as e:
                logger.error(f"Ошибка генерации вопросов для лида {lead.id}: {e}", exc_info=True)
                # Fallback: переходим в обычный FREE_CHAT
                await callback.message.answer(
                    "Напишите ваш вопрос:",
                    reply_markup=get_free_chat_keyboard(show_meeting=show_meeting),
                )
                await state.set_state(ConversationState.FREE_CHAT)
                await callback.answer()
        else:
            # Если лид не найден — обычный FREE_CHAT
            await callback.message.answer(
                "Напишите ваш вопрос:",
                reply_markup=get_free_chat_keyboard(show_meeting=show_meeting),
            )
            await state.set_state(ConversationState.FREE_CHAT)
            await callback.answer()

    elif action == "restart":
        await state.clear()

        # AICODE-NOTE: Динамический импорт для избежания циклических зависимостей
        from src.handlers.start import cmd_start

        await cmd_start(callback.message, state)
        await callback.answer()


# =============================================================================
# MESSAGE HANDLERS для текстового ввода
# =============================================================================


@router.message(ConversationState.TASK_CUSTOM_INPUT, F.text)
async def handle_task_custom_input(message: Message, state: FSMContext) -> None:
    """Обработка текстового ввода задачи (после выбора 'Своя задача')."""
    if not message.from_user or not message.text:
        return

    task = message.text.strip()

    # Сохраняем в FSM context
    await state.update_data(task=task)

    # Получаем лида и сохраняем в БД
    lead = await Lead.get_or_none(telegram_id=message.from_user.id)
    if lead:
        lead.task = task
        await _update_last_message_time(lead)

        # Сохраняем в историю диалога
        await Conversation.create(
            lead=lead,
            role=MessageRole.USER,
            content=task,
        )

    # Отправляем подтверждение и следующий вопрос
    progress = get_progress_indicator("BUDGET")
    await message.answer(
        f"Задача: {task}\n\n{progress}\n\nКакой примерный бюджет?\n\n"
        f"_Выберите вариант или напишите свой:_",
        reply_markup=get_budget_keyboard(),
        parse_mode="Markdown",
    )

    await state.set_state(ConversationState.BUDGET)

    logger.info(f"Лид {lead.id if lead else '?'} ввёл задачу: {task[:50]}")


@router.message(ConversationState.BUDGET_CUSTOM_INPUT, F.text)
async def handle_budget_custom_input(message: Message, state: FSMContext) -> None:
    """Обработка текстового ввода бюджета (после выбора 'Свой вариант')."""
    if not message.from_user or not message.text:
        return

    budget = message.text.strip()

    # Сохраняем в FSM context
    await state.update_data(budget=budget)

    # Получаем лида и сохраняем в БД
    lead = await Lead.get_or_none(telegram_id=message.from_user.id)
    if lead:
        lead.budget = budget
        await _update_last_message_time(lead)

        # Сохраняем в историю диалога
        await Conversation.create(
            lead=lead,
            role=MessageRole.USER,
            content=f"[Бюджет: {budget}]",
        )

    # Получаем данные для показа
    fsm_data = await state.get_data()
    task = fsm_data.get("task", "—")

    # Отправляем подтверждение и следующий вопрос
    progress = get_progress_indicator("DEADLINE")
    await message.answer(
        f"Задача: {task}\nБюджет: {budget}\n\n{progress}\n\nКогда нужен результат?\n\n"
        f"_Выберите вариант или напишите свой:_",
        reply_markup=get_deadline_keyboard(),
        parse_mode="Markdown",
    )

    await state.set_state(ConversationState.DEADLINE)

    logger.info(f"Лид {lead.id if lead else '?'} ввёл бюджет: {budget}")


@router.message(ConversationState.DEADLINE_CUSTOM_INPUT, F.text)
async def handle_deadline_custom_input(message: Message, state: FSMContext) -> None:
    """Обработка текстового ввода срока (после выбора 'Свой вариант').

    Выполняет квалификацию на основе введённых данных.
    """
    if not message.from_user or not message.text:
        return

    deadline = message.text.strip()

    # Сохраняем в FSM context
    await state.update_data(deadline=deadline)

    # Получаем лида
    lead = await Lead.get_or_none(telegram_id=message.from_user.id)
    if not lead:
        await message.answer("Начните диалог с команды /start")
        return

    # Сохраняем срок в БД
    lead.deadline = deadline
    await _update_last_message_time(lead)

    await Conversation.create(
        lead=lead,
        role=MessageRole.USER,
        content=f"[Срок: {deadline}]",
    )

    # Получаем все данные для квалификации
    fsm_data = await state.get_data()
    task = fsm_data.get("task", "—")
    budget = fsm_data.get("budget", "—")

    # Квалификация для custom ввода — используем эвристику
    # AICODE-NOTE: Для custom ввода используем более мягкую квалификацию
    new_status = _qualify_lead_custom(deadline, budget)
    old_status = lead.status
    lead.status = new_status
    await lead.save()

    # Определяем, нужно ли уведомлять владельца
    status_priority = {LeadStatus.NEW: 0, LeadStatus.COLD: 1, LeadStatus.WARM: 2, LeadStatus.HOT: 3}
    status_upgraded = status_priority.get(new_status, 0) > status_priority.get(old_status, 0)

    logger.info(
        f"Лид {lead.id} квалифицирован (custom): {old_status.value} → {new_status.value} "
        f"(notify={status_upgraded})"
    )

    # Формируем сообщение на основе статуса
    summary = f"Задача: {task}\nБюджет: {budget}\nСроки: {deadline}\n\n"

    if new_status == LeadStatus.HOT:
        message_text = (
            summary + "Отлично, проект срочный!\n\n"
            f"Предлагаю назначить звонок с {settings.business_name} — обсудим детали."
        )
    elif new_status == LeadStatus.WARM:
        message_text = (
            summary + "Понял, спасибо за информацию.\n\n"
            "Могу отправить примеры наших работ или ответить на вопросы."
        )
    else:  # COLD
        message_text = (
            summary + "Спасибо за интерес!\n\n"
            "Могу отправить материалы для ознакомления или ответить на вопросы."
        )

    await message.answer(message_text, reply_markup=get_action_keyboard(new_status))

    await state.set_state(ConversationState.ACTION)

    # Сохраняем флаг для отложенного уведомления (если лид назначит встречу — уведомим там)
    if status_upgraded and new_status in [LeadStatus.HOT, LeadStatus.WARM]:
        await state.update_data(pending_lead_notification=True)
        logger.info(f"Отложено уведомление о лиде {lead.id} (pending_lead_notification=True)")


async def _handle_free_chat_logic(message: Message, state: FSMContext) -> None:
    """
    Внутренняя логика обработки свободного диалога.

    Вынесено в отдельную функцию для возможности вызова из разных мест
    (FSM handler и fallback handler).

    Включает счётчик вопросов — после N вопросов предлагает назначить встречу.

    Args:
        message: Сообщение от пользователя
        state: FSM context для хранения счётчика вопросов
    """
    if not message.from_user or not message.text:
        return

    user_message = message.text

    lead = await Lead.get_or_none(telegram_id=message.from_user.id)
    if not lead:
        await message.answer("Начните диалог с команды /start")
        return

    # Обновляем время последнего сообщения
    await _update_last_message_time(lead)

    # Сохраняем сообщение в историю
    await Conversation.create(
        lead=lead,
        role=MessageRole.USER,
        content=user_message,
    )

    # Инкрементируем счётчик вопросов в FREE_CHAT
    fsm_data = await state.get_data()
    free_chat_count = fsm_data.get("free_chat_count", 0) + 1
    await state.update_data(free_chat_count=free_chat_count)

    max_q = settings.free_chat_max_questions
    logger.info(f"FREE_CHAT от лида {lead} ({free_chat_count}/{max_q}): {user_message[:50]}")

    # Определяем, показывать ли кнопку встречи
    show_meeting = lead.status != LeadStatus.COLD

    # Генерируем ответ через LLM
    try:
        response_data: LLMResponse = await generate_response_free_chat(lead, user_message)
        bot_response = response_data["response"]

        # Сохраняем ответ бота
        await Conversation.create(
            lead=lead,
            role=MessageRole.ASSISTANT,
            content=bot_response,
        )

        # Проверяем, достигнут ли лимит вопросов
        if free_chat_count >= settings.free_chat_max_questions and show_meeting:
            # Предлагаем встречу более явно
            await message.answer(
                f"{bot_response}\n\n"
                f"───────────────────\n"
                f"💡 Мы уже обсудили несколько вопросов. Давайте назначим встречу — "
                f"так будет быстрее разобраться во всех деталях!",
                reply_markup=get_meeting_suggestion_keyboard(),
            )
            # Сбрасываем счётчик для следующего цикла
            await state.update_data(free_chat_count=0)
        else:
            await message.answer(
                bot_response, reply_markup=get_free_chat_keyboard(show_meeting=show_meeting)
            )

    except Exception as e:
        logger.error(f"Ошибка LLM для лида {lead.id}: {e}", exc_info=True)
        await message.answer(
            "Извините, произошла ошибка. Попробуйте переформулировать вопрос.",
            reply_markup=get_free_chat_keyboard(show_meeting=show_meeting),
        )


@router.message(ConversationState.FREE_CHAT, F.text)
async def handle_free_chat(message: Message, _state: FSMContext) -> None:
    """Обработка сообщений в свободном диалоге через LLM (FSM handler)."""
    await _handle_free_chat_logic(message, _state)


# =============================================================================
# FALLBACK HANDLERS
# =============================================================================


@router.message(F.text)
async def handle_message_without_state(message: Message, state: FSMContext) -> None:
    """Обработка сообщений от лидов без активного state (fallback)."""
    if not message.from_user or not message.text:
        return

    current_state = await state.get_state()

    # Если state не установлен — направляем на начало диалога
    if not current_state:
        lead = await Lead.get_or_none(telegram_id=message.from_user.id)

        # Сохраняем сообщение если лид существует
        if lead:
            await _update_last_message_time(lead)
            await Conversation.create(
                lead=lead,
                role=MessageRole.USER,
                content=message.text,
            )

        await message.answer(
            "Давайте начнем сначала! 😊\n\nНажмите /start или выберите задачу:",
            reply_markup=get_task_keyboard(),
        )
        await state.set_state(ConversationState.TASK)
        return

    # Если state BUDGET — предлагаем ввести текстом или выбрать
    if current_state == ConversationState.BUDGET.state:
        # Обрабатываем как custom input
        await state.set_state(ConversationState.BUDGET_CUSTOM_INPUT)
        await handle_budget_custom_input(message, state)
        return

    # Если state DEADLINE — предлагаем ввести текстом или выбрать
    if current_state == ConversationState.DEADLINE.state:
        # Обрабатываем как custom input
        await state.set_state(ConversationState.DEADLINE_CUSTOM_INPUT)
        await handle_deadline_custom_input(message, state)
        return

    # Для других states перенаправляем в свободный диалог
    await state.set_state(ConversationState.FREE_CHAT)
    # AICODE-NOTE: Вызываем _handle_free_chat_logic напрямую, т.к. handle_free_chat
    # зарегистрирован как FSM handler и ожидает вызова через роутер
    await _handle_free_chat_logic(message, state)


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================


def _qualify_lead_custom(deadline: str, budget: str) -> LeadStatus:
    """Квалификация лида с произвольным вводом бюджета/срока.

    Использует эвристику для анализа текста.

    Args:
        deadline: Текстовое описание срока
        budget: Текстовое описание бюджета

    Returns:
        LeadStatus (HOT, WARM, COLD)
    """
    # AICODE-NOTE: Простая эвристика для MVP.
    # В будущем можно использовать LLM для анализа.

    deadline_lower = deadline.lower()
    budget_lower = budget.lower()

    # Паттерны срочности
    urgent_patterns = ["срочно", "сегодня", "завтра", "неделя", "этой недел", "asap", "быстро"]
    soon_patterns = ["месяц", "этом месяце", "скоро", "ближайш", "пару недел", "2 недел"]

    # Паттерны высокого бюджета
    high_budget_patterns = ["150", "200", "300", "500", "миллион", "1м", "1 м"]
    medium_budget_patterns = ["50", "60", "70", "80", "90", "100", "сто"]

    # Определяем срочность
    is_urgent = any(pattern in deadline_lower for pattern in urgent_patterns)
    is_soon = any(pattern in deadline_lower for pattern in soon_patterns)

    # Определяем бюджет
    is_high_budget = any(pattern in budget_lower for pattern in high_budget_patterns)
    is_medium_budget = any(pattern in budget_lower for pattern in medium_budget_patterns)

    # Квалификация
    if is_urgent and (is_high_budget or is_medium_budget):
        return LeadStatus.HOT

    if is_high_budget and (is_urgent or is_soon):
        return LeadStatus.HOT

    if is_soon or is_medium_budget or is_urgent:
        return LeadStatus.WARM

    # По умолчанию — WARM для custom ввода (показывает заинтересованность)
    return LeadStatus.WARM


def _qualify_lead(deadline_type: str, budget: str) -> LeadStatus:
    """Квалификация лида на основе срока и бюджета.

    Правила квалификации:
    - HOT: срочно + средний/высокий бюджет ИЛИ высокий бюджет + не отложено
    - WARM: средний бюджет ИЛИ скоро ИЛИ срочно с любым бюджетом
    - COLD: остальные случаи

    Args:
        deadline_type: Тип срока (urgent, soon, later)
        budget: Текстовое значение бюджета

    Returns:
        LeadStatus (HOT, WARM, COLD)
    """
    # AICODE-NOTE: Простая rule-based квалификация для MVP.
    # В будущем можно добавить более сложную логику или ML.

    # Горячий лид: срочно + бюджет от среднего и выше
    if deadline_type == "urgent" and budget in ["50 000 - 150 000 ₽", "150 000+ ₽"]:
        return LeadStatus.HOT

    # Горячий лид: высокий бюджет + не отложенный срок
    if budget == "150 000+ ₽" and deadline_type != "later":
        return LeadStatus.HOT

    # Тёплый лид: средний бюджет или скоро
    if deadline_type == "soon" or budget == "50 000 - 150 000 ₽":
        return LeadStatus.WARM

    # Тёплый лид: срочно + любой бюджет (но не высокий — уже HOT)
    if deadline_type == "urgent":
        return LeadStatus.WARM

    # Холодный лид: остальные случаи
    return LeadStatus.COLD


async def _send_materials(message: Message, lead: Lead | None) -> None:
    """Отправляет материалы (портфолио, кейсы, презентация).

    Args:
        message: Сообщение для ответа
        lead: Объект лида (для логирования)
    """
    materials_text = "📂 **Наши материалы:**\n\n"
    materials_added = False

    if settings.portfolio_url:
        materials_text += f"🌐 **Портфолио:** {settings.portfolio_url}\n"
        materials_added = True

    if settings.cases_url:
        materials_text += f"📋 **Кейсы:** {settings.cases_url}\n"
        materials_added = True

    if settings.presentation_url:
        materials_text += f"📊 **Презентация:** {settings.presentation_url}\n"
        materials_added = True

    if materials_added:
        await message.answer(materials_text, parse_mode="Markdown")
        logger.info(f"Отправлены материалы лиду {lead.id if lead else '?'}")
    else:
        # AICODE-NOTE: Если материалы не настроены, отправляем заглушку
        await message.answer(
            "📂 Материалы скоро будут доступны!\n\n"
            "Пока можете задать любой вопрос — буду рад помочь.",
            parse_mode="Markdown",
        )
        logger.warning("Материалы не настроены (пустые URL в .env)")


def create_router() -> Router:
    """Создаёт новый роутер для conversation handlers (для тестов)."""
    new_router = Router(name="conversation")
    # Callback handlers
    new_router.callback_query.register(handle_task_callback, F.data.startswith("task:"))
    new_router.callback_query.register(handle_budget_callback, F.data.startswith("budget:"))
    new_router.callback_query.register(handle_deadline_callback, F.data.startswith("deadline:"))
    new_router.callback_query.register(handle_question_callback, F.data.startswith("question:"))
    new_router.callback_query.register(handle_action_callback, F.data.startswith("action:"))
    # Message handlers
    new_router.message.register(
        handle_task_custom_input, ConversationState.TASK_CUSTOM_INPUT, F.text
    )
    new_router.message.register(
        handle_budget_custom_input, ConversationState.BUDGET_CUSTOM_INPUT, F.text
    )
    new_router.message.register(
        handle_deadline_custom_input, ConversationState.DEADLINE_CUSTOM_INPUT, F.text
    )
    new_router.message.register(handle_free_chat, ConversationState.FREE_CHAT, F.text)
    new_router.message.register(handle_message_without_state, F.text)
    return new_router
