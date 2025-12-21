"""Типы данных для типизации проекта."""

from typing import Literal, TypedDict

from src.database.models import LeadStatus

# AICODE-NOTE: Используем TypedDict вместо Dict[str, Any] для строгой типизации
# ответов от LLM и других структурированных данных


class LLMResponse(TypedDict):
    """Структурированный ответ от LLM (Claude API)."""

    response: str
    status: LeadStatus
    action: Literal["continue", "schedule_meeting", "send_materials"]


class LLMResponseRaw(TypedDict):
    """Сырой ответ от LLM в JSON формате (до парсинга)."""

    response: str
    status: str
    action: str
    reasoning: str


# Алиасы типов для улучшения читаемости
TelegramID = int
MessageText = str
Username = str | None
