"""Тесты для конфигурации приложения."""

from src.config import settings


def test_settings_loaded() -> None:
    """Проверка загрузки настроек из .env."""
    # Проверяем, что тестовые переменные загрузились
    assert settings.telegram_bot_token == "test_token_123456"
    assert settings.anthropic_api_key == "test_api_key"
    assert settings.database_url == "sqlite://:memory:"


def test_settings_defaults() -> None:
    """Проверка дефолтных значений настроек."""
    assert settings.business_name == "Test Business"
    assert settings.mode == "test"


def test_owner_telegram_id() -> None:
    """Проверка owner_telegram_id."""
    assert settings.owner_telegram_id == 123456789
