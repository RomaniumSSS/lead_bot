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

    # Bot Mode
    bot_mode: str = "polling"  # polling | webhook

    # Webhook настройки (только для bot_mode=webhook)
    webhook_url: str | None = None  # https://yourdomain.com/webhook
    webhook_path: str = "/webhook"
    webhook_port: int = 8080

    # Materials for warm leads (action="send_materials")
    portfolio_url: str | None = None
    cases_url: str | None = None
    presentation_url: str | None = None

    # FREE_CHAT settings
    free_chat_max_questions: int = 5  # После N вопросов предложить встречу


# Глобальный экземпляр настроек
# AICODE-NOTE: Settings автоматически загружает переменные из .env
settings = Settings(_env_file=".env")  # type: ignore[call-arg]
