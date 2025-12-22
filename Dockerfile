FROM python:3.11-slim

# Установка uv через pip (официальный способ для Docker)
RUN pip install --no-cache-dir uv

# Рабочая директория
WORKDIR /app

# Копирование файлов зависимостей
COPY pyproject.toml ./

# Установка зависимостей
RUN uv sync --no-dev

# Копирование исходного кода
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY healthcheck.py ./healthcheck.py

# Создание директории для логов
RUN mkdir -p /app/logs

# Команда запуска
CMD ["uv", "run", "python", "-m", "src.bot"]
