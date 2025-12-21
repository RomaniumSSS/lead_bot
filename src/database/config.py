"""Конфигурация Tortoise ORM для подключения к базе данных."""

from typing import Any

from src.config import settings

# AICODE-NOTE: Tortoise ORM требует специфическую структуру конфига,
# поэтому используем Dict[str, Any] вместо TypedDict
TORTOISE_ORM: dict[str, Any] = {
    "connections": {"default": settings.database_url},
    "apps": {
        "models": {
            "models": ["src.database.models", "aerich.models"],
            "default_connection": "default",
        }
    },
    "use_tz": False,
    "timezone": "UTC",
}
