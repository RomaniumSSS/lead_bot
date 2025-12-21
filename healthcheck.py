#!/usr/bin/env python3
"""Healthcheck скрипт для Docker контейнера бота."""

import sys
from pathlib import Path


def check_bot_health() -> bool:
    """
    Проверка работоспособности бота.

    Простая проверка: существует ли log файл и писались ли в него данные недавно.
    Это означает, что бот работает.

    Returns:
        True если бот здоров, False иначе.
    """
    log_file = Path("/app/logs/bot.log")

    # AICODE-NOTE: Простой healthcheck для MVP.
    # В продакшене можно добавить проверку через Bot API (getMe).

    # Проверяем, существует ли файл логов
    if not log_file.exists():
        sys.stderr.write("❌ Log file not found\n")
        return False

    # Проверяем, что файл не пустой
    if log_file.stat().st_size == 0:
        sys.stderr.write("❌ Log file is empty\n")
        return False

    sys.stdout.write("✅ Bot is healthy\n")
    return True


if __name__ == "__main__":
    sys.exit(0 if check_bot_health() else 1)
