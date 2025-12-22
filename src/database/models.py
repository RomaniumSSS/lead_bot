"""Модели базы данных Tortoise ORM."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from tortoise import Model, fields
from tortoise.contrib.pydantic import pydantic_model_creator

if TYPE_CHECKING:
    from tortoise.queryset import QuerySet


class LeadStatus(str, Enum):
    """Статус лида."""

    NEW = "new"  # Новый (только что написал)
    COLD = "cold"  # Холодный (не квалифицирован, низкий интерес)
    WARM = "warm"  # Тёплый (квалифицирован, средний интерес)
    HOT = "hot"  # Горячий (готов к встрече, высокий интерес)


class MessageRole(str, Enum):
    """Роль отправителя сообщения."""

    USER = "user"  # Лид
    ASSISTANT = "assistant"  # Бот


class MeetingStatus(str, Enum):
    """Статус встречи."""

    SCHEDULED = "scheduled"  # Назначена
    COMPLETED = "completed"  # Прошла
    CANCELLED = "cancelled"  # Отменена


class Lead(Model):
    """Модель лида (потенциального клиента)."""

    id = fields.IntField(pk=True)
    telegram_id = fields.BigIntField(unique=True, description="Telegram User ID")
    # AICODE-NOTE: Tortoise ORM не поддерживает аннотации типов напрямую,
    # используем type: ignore для совместимости с MyPy
    username: str | None = fields.CharField(
        max_length=255, null=True, description="@username в Telegram"
    )  # type: ignore[assignment]
    first_name: str | None = fields.CharField(max_length=255, null=True, description="Имя")  # type: ignore[assignment]
    last_name: str | None = fields.CharField(max_length=255, null=True, description="Фамилия")  # type: ignore[assignment]

    # Квалификация
    status = fields.CharEnumField(LeadStatus, default=LeadStatus.NEW, description="Статус лида")
    task: str | None = fields.TextField(null=True, description="Какая задача у лида")  # type: ignore[assignment]
    budget: str | None = fields.CharField(max_length=255, null=True, description="Бюджет")  # type: ignore[assignment]
    deadline: str | None = fields.CharField(
        max_length=255, null=True, description="Когда нужно решить"
    )  # type: ignore[assignment]

    # Метаданные
    created_at = fields.DatetimeField(auto_now_add=True, description="Дата создания")
    updated_at = fields.DatetimeField(auto_now=True, description="Дата обновления")
    last_message_at = fields.DatetimeField(null=True, description="Последнее сообщение от лида")
    follow_up_count = fields.IntField(default=0, description="Количество отправленных follow-up")

    # Связи (reverse relations)
    # AICODE-NOTE: ReverseRelation типизируется через QuerySet для корректной работы с MyPy
    if TYPE_CHECKING:
        conversations: QuerySet[Conversation]
        meetings: QuerySet[Meeting]

    class Meta:
        table = "leads"

    def __str__(self) -> str:
        name = self.first_name or self.username or f"User {self.telegram_id}"
        return f"Lead({name}, {self.status.value})"


class Conversation(Model):
    """Модель диалога (история сообщений)."""

    id = fields.IntField(pk=True)
    lead: fields.ForeignKeyRelation[Lead] = fields.ForeignKeyField(
        "models.Lead",
        related_name="conversations",
        on_delete=fields.CASCADE,
        description="Связанный лид",
    )

    role = fields.CharEnumField(MessageRole, description="Роль отправителя")
    content = fields.TextField(description="Текст сообщения")

    created_at = fields.DatetimeField(auto_now_add=True, description="Дата отправки")

    class Meta:
        table = "conversations"
        ordering = ["created_at"]

    def __str__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"Message({self.role.value}: {preview})"


class Meeting(Model):
    """Модель встречи с лидом."""

    id = fields.IntField(pk=True)
    lead: fields.ForeignKeyRelation[Lead] = fields.ForeignKeyField(
        "models.Lead",
        related_name="meetings",
        on_delete=fields.CASCADE,
        description="Связанный лид",
    )

    scheduled_at = fields.DatetimeField(description="Дата и время встречи")
    status = fields.CharEnumField(
        MeetingStatus, default=MeetingStatus.SCHEDULED, description="Статус встречи"
    )
    notes = fields.TextField(null=True, description="Заметки о встрече")

    created_at = fields.DatetimeField(auto_now_add=True, description="Дата создания")
    updated_at = fields.DatetimeField(auto_now=True, description="Дата обновления")

    class Meta:
        table = "meetings"
        ordering = ["-scheduled_at"]

    def __str__(self) -> str:
        return f"Meeting({self.scheduled_at}, {self.status.value})"


# Pydantic модели для сериализации (опционально, для будущих API)
LeadPydantic = pydantic_model_creator(Lead, name="Lead")
ConversationPydantic = pydantic_model_creator(Conversation, name="Conversation")
MeetingPydantic = pydantic_model_creator(Meeting, name="Meeting")
