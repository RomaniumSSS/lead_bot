"""Handler для структурированного диалога с лидами через FSM."""

from datetime import datetime

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
# CALLBACK HANDLERS для кнопок
# =============================================================================


@router.callback_query(F.data.startswith("task:"))
async def handle_task_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка выбора задачи через кнопку."""
    if not callback.data or not callback.message or not callback.from_user:
        return

    # AICODE-NOTE: Проверка типа сообщения для корректной работы с MyPy
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    task_type = callback.data.split(":")[1]

    # Если выбрана "Своя задача" — просим ввести текстом
    if task_type == "custom":
        await callback.message.edit_reply_markup(reply_markup=None)

        progress = get_progress_indicator("TASK")
        await callback.message.answer(
            f"─────────────────\n{progress}\n─────────────────\n\n"
            "Напишите, пожалуйста, какая задача у вас есть:"
        )
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
        lead.last_message_at = datetime.utcnow()
        await lead.save()

        # Сохраняем в историю диалога
        await Conversation.create(
            lead=lead,
            role=MessageRole.USER,
            content=f"[Выбрана задача: {task}]",
        )

    # Убираем старую клавиатуру
    await callback.message.edit_reply_markup(reply_markup=None)

    # Отправляем подтверждение и следующий вопрос
    progress = get_progress_indicator("BUDGET")
    await callback.message.answer(
        f"✅ **Задача:** {task}\n\n"
        f"─────────────────\n{progress}\n─────────────────\n\n"
        f"Какой у вас примерный бюджет на проект?",
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

    budget_type = callback.data.split(":")[1]
    budget = BUDGET_LABELS.get(budget_type, "Не указан")

    # Сохраняем в FSM context
    await state.update_data(budget=budget)

    # Получаем лида и сохраняем в БД
    lead = await Lead.get_or_none(telegram_id=callback.from_user.id)
    if lead:
        lead.budget = budget
        lead.last_message_at = datetime.utcnow()
        await lead.save()

        # Сохраняем в историю диалога
        await Conversation.create(
            lead=lead,
            role=MessageRole.USER,
            content=f"[Выбран бюджет: {budget}]",
        )

    # Убираем старую клавиатуру
    await callback.message.edit_reply_markup(reply_markup=None)

    # Получаем данные для показа прогресса
    fsm_data = await state.get_data()
    task = fsm_data.get("task", "—")

    # Отправляем подтверждение и следующий вопрос
    progress = get_progress_indicator("DEADLINE")
    await callback.message.answer(
        f"✅ **Задача:** {task}\n"
        f"✅ **Бюджет:** {budget}\n\n"
        f"─────────────────\n{progress}\n─────────────────\n\n"
        f"Когда нужно завершить проект?",
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
    lead.last_message_at = datetime.utcnow()

    # Сохраняем в историю диалога
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

    logger.info(f"Лид {lead.id} квалифицирован: {old_status.value} → {new_status.value}")

    # Убираем старую клавиатуру
    await callback.message.edit_reply_markup(reply_markup=None)

    # Формируем сообщение на основе статуса
    progress = get_progress_indicator("ACTION")
    summary = (
        f"✅ **Задача:** {task}\n"
        f"✅ **Бюджет:** {budget}\n"
        f"✅ **Срок:** {deadline}\n\n"
        f"─────────────────\n{progress}\n─────────────────\n\n"
    )

    if new_status == LeadStatus.HOT:
        message_text = (
            summary + f"🔥 **Отлично!** Проект срочный и важный.\n\n"
            f"Давайте назначим встречу с владельцем {settings.business_name}, "
            f"чтобы обсудить детали?"
        )
    elif new_status == LeadStatus.WARM:
        message_text = (
            summary + "👍 **Понял!** Отправлю вам наши кейсы и материалы.\n\n"
            "Что хотите сделать дальше?"
        )
    else:  # COLD or NEW
        message_text = (
            summary + "💬 **Спасибо за интерес!** Буду на связи.\n\nЕсли появятся вопросы — пишите!"
        )

    await callback.message.answer(message_text, reply_markup=get_action_keyboard(new_status))

    await state.set_state(ConversationState.ACTION)
    await callback.answer()

    # Уведомляем владельца о новом лиде
    if new_status in [LeadStatus.HOT, LeadStatus.WARM]:
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

    if action == "schedule_meeting":
        # AICODE-NOTE: Локальный импорт для избежания циклических зависимостей
        from src.handlers.meetings import propose_meeting_times

        if lead:
            await callback.message.edit_reply_markup(reply_markup=None)
            await propose_meeting_times(lead, callback.message)
        await callback.answer()

    elif action == "send_materials":
        await callback.message.edit_reply_markup(reply_markup=None)
        await _send_materials(callback.message, lead)
        await callback.answer()

        # Переход в свободный диалог
        await callback.message.answer(
            "Если появятся вопросы — пишите! Буду рад помочь. 😊",
            reply_markup=get_free_chat_keyboard(),
        )
        await state.set_state(ConversationState.FREE_CHAT)

    elif action == "free_chat":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "Отлично! Напишите ваш вопрос, и я постараюсь помочь. 💬",
            reply_markup=get_free_chat_keyboard(),
        )
        await state.set_state(ConversationState.FREE_CHAT)
        await callback.answer()

    elif action == "restart":
        await callback.message.edit_reply_markup(reply_markup=None)
        await state.clear()

        # AICODE-NOTE: Локальный импорт для избежания циклических зависимостей
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
        lead.last_message_at = datetime.utcnow()
        await lead.save()

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
    lead.last_message_at = datetime.utcnow()
    await lead.save()

    # Сохраняем сообщение в историю
    await Conversation.create(
        lead=lead,
        role=MessageRole.USER,
        content=user_message,
    )

    logger.info(f"Сообщение в FREE_CHAT от лида {lead}: {user_message[:50]}")

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

        await message.answer(bot_response, reply_markup=get_free_chat_keyboard())

    except Exception as e:
        logger.error(f"Ошибка LLM для лида {lead.id}: {e}", exc_info=True)
        await message.answer(
            "Извините, произошла ошибка. Попробуйте переформулировать вопрос.",
            reply_markup=get_free_chat_keyboard(),
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
            lead.last_message_at = datetime.utcnow()
            await lead.save()
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
