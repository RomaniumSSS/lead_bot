"""Тесты для типов данных."""

from typing import get_args

from src.database.models import LeadStatus
from src.types import LLMResponse, LLMResponseRaw


def test_llm_response_type() -> None:
    """Тест структуры LLMResponse."""
    # Проверяем, что TypedDict содержит нужные поля
    annotations = LLMResponse.__annotations__

    assert "response" in annotations
    assert "status" in annotations
    assert "action" in annotations

    # Проверяем типы
    assert annotations["response"] is str
    assert annotations["status"] is LeadStatus

    # Проверяем Literal action
    action_type = annotations["action"]
    action_values = get_args(action_type)
    assert "continue" in action_values
    assert "schedule_meeting" in action_values
    assert "send_materials" in action_values


def test_llm_response_raw_type() -> None:
    """Тест структуры LLMResponseRaw."""
    annotations = LLMResponseRaw.__annotations__

    assert "response" in annotations
    assert "status" in annotations
    assert "action" in annotations
    assert "reasoning" in annotations

    # Все поля должны быть строками
    assert annotations["response"] is str
    assert annotations["status"] is str
    assert annotations["action"] is str
    assert annotations["reasoning"] is str


def test_create_llm_response() -> None:
    """Тест создания LLMResponse."""
    response: LLMResponse = {
        "response": "Привет! Чем могу помочь?",
        "status": LeadStatus.NEW,
        "action": "continue",
    }

    assert response["response"] == "Привет! Чем могу помочь?"
    assert response["status"] == LeadStatus.NEW
    assert response["action"] == "continue"
