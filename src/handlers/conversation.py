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
    get_progress_indicator,
    get_task_keyboard,
)
from src.services.llm import generate_response_free_chat
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

    # Уведомляем владельца только при ПОВЫШЕНИИ статуса до HOT или WARM
    if status_upgraded and new_status in [LeadStatus.HOT, LeadStatus.WARM]:
        try:
            await notify_owner_about_lead(lead)
        except Exception as e:
            logger.error(f"Ошибка уведомления владельца о лиде {lead.id}: {e}")


@router.callback_query(F.data.startswith("action:"))
async def handle_action_callback(callback: CallbackQuery, state: FSMContext) -> None:
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

        from src.handlers.meetings import propose_meeting_times

        if lead:
            await propose_meeting_times(lead, callback.message)
        await callback.answer()

    elif action == "send_materials":
        await _send_materials(callback.message, lead)
        await callback.answer()

        # Переход в свободный диалог
        await callback.message.answer(
            "Если есть вопросы — пишите, отвечу.",
            reply_markup=get_free_chat_keyboard(show_meeting=show_meeting),
        )
        await state.set_state(ConversationState.FREE_CHAT)

    elif action == "free_chat":
        await callback.message.answer(
            "Напишите ваш вопрос.",
            reply_markup=get_free_chat_keyboard(show_meeting=show_meeting),
        )
        await state.set_state(ConversationState.FREE_CHAT)
        await callback.answer()

    elif action == "restart":
        await state.clear()

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
        f"✅ **Задача:** {task}\n\n"
        f"─────────────────\n{progress}\n─────────────────\n\n"
        f"Какой у вас примерный бюджет на проект?",
        reply_markup=get_budget_keyboard(),
    )

    await state.set_state(ConversationState.BUDGET)

    logger.info(f"Лид {lead.id if lead else '?'} ввёл задачу: {task[:50]}")


@router.message(ConversationState.FREE_CHAT, F.text)
async def handle_free_chat(message: Message, _state: FSMContext) -> None:
    """Обработка сообщений в свободном диалоге через LLM."""
    # AICODE-NOTE: _state требуется aiogram для FSM handler, но не используется здесь
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

    logger.info(f"Сообщение в FREE_CHAT от лида {lead}: {user_message[:50]}")

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

        await message.answer(
            bot_response, reply_markup=get_free_chat_keyboard(show_meeting=show_meeting)
        )

    except Exception as e:
        logger.error(f"Ошибка LLM для лида {lead.id}: {e}", exc_info=True)
        await message.answer(
            "Извините, произошла ошибка. Попробуйте переформулировать вопрос.",
            reply_markup=get_free_chat_keyboard(show_meeting=show_meeting),
        )


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

    # Если есть state, но ожидаем кнопку — мягко напоминаем
    # (например, пользователь написал текст вместо выбора бюджета)
    if current_state in [
        ConversationState.BUDGET.state,
        ConversationState.DEADLINE.state,
    ]:
        await message.answer(
            "Пожалуйста, выберите один из вариантов выше 👆\n\n"
            "Или нажмите /restart чтобы начать заново."
        )
        return

    # Для других states перенаправляем в свободный диалог
    await state.set_state(ConversationState.FREE_CHAT)
    await handle_free_chat(message, state)


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================


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
