"""Настройка логирования для приложения."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from src.config import settings


def setup_logger(name: str = "ai-sales-assistant") -> logging.Logger:
    """
    Настраивает логгер для приложения.

    Args:
        name: Имя логгера

    Returns:
        Настроенный логгер
    """
    logger: logging.Logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper()))

    # Удаляем существующие handlers (если есть)
    logger.handlers.clear()

    # Формат логов
    formatter: logging.Formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (вывод в терминал)
    console_handler: logging.StreamHandler[Any] = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (запись в файл)
    logs_dir: Path = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    file_handler: RotatingFileHandler = RotatingFileHandler(
        logs_dir / "bot.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# Глобальный логгер
logger = setup_logger()
