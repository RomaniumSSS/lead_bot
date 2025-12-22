FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка uv и настройка PATH
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Рабочая директория
WORKDIR /app

# Копирование файлов зависимостей
COPY pyproject.toml ./

# Установка зависимостей (используем полный путь)
RUN /root/.cargo/bin/uv sync --no-dev

# Копирование исходного кода
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY healthcheck.py ./healthcheck.py

# Создание директории для логов
RUN mkdir -p /app/logs

# Команда запуска
CMD ["/root/.cargo/bin/uv", "run", "python", "-m", "src.bot"]
