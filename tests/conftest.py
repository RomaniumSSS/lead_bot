"""Pytest конфигурация и фикстуры."""

import os
from collections.abc import AsyncGenerator

import pytest
from tortoise import Tortoise

# Устанавливаем тестовые переменные окружения
os.environ["TELEGRAM_BOT_TOKEN"] = "test_token_123456"
os.environ["ANTHROPIC_API_KEY"] = "test_api_key"
os.environ["DATABASE_URL"] = "sqlite://:memory:"
os.environ["OWNER_TELEGRAM_ID"] = "123456789"
os.environ["BUSINESS_NAME"] = "Test Business"
os.environ["BUSINESS_DESCRIPTION"] = "Test Description"
os.environ["MODE"] = "test"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Backend для anyio (используется pytest-asyncio)."""
    return "asyncio"


@pytest.fixture(autouse=True)
async def initialize_db() -> AsyncGenerator[None, None]:
    """
    Инициализация тестовой БД перед каждым тестом.

    Используется in-memory SQLite для скорости.
    После каждого теста БД очищается.
    """
    # Инициализация Tortoise ORM с in-memory SQLite
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["src.database.models"]},
    )
    await Tortoise.generate_schemas()

    yield

    # Очистка после теста
    await Tortoise.close_connections()


@pytest.fixture
def test_telegram_id() -> int:
    """Тестовый Telegram ID."""
    return 987654321


@pytest.fixture
def test_username() -> str:
    """Тестовый username."""
    return "test_user"
