"""Конфигурация приложения через .env файл."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Игнорируем лишние переменные из .env
    )

    # Telegram Bot
    telegram_bot_token: str

    # Anthropic Claude
    anthropic_api_key: str = "test-key"  # Дефолт для тестов

    # Database
    database_url: str

    # Owner (опционально для разработки)
    owner_telegram_id: int | None = None

    # Business Info
    business_name: str = "Тестовый Бизнес"
    business_description: str = "Тестовое описание"

    # Application
    mode: str = "development"
    log_level: str = "INFO"


# Глобальный экземпляр настроек
# AICODE-NOTE: Settings автоматически загружает переменные из .env
settings = Settings(_env_file=".env")  # type: ignore[call-arg]
