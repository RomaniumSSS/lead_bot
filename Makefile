.PHONY: help install run dev migrate migrate-create upgrade lint format type-check test test-cov clean docker-build docker-up docker-down docker-logs docker-restart

# Цвета для вывода
GREEN  := \033[0;32m
YELLOW := \033[0;33m
BLUE   := \033[0;34m
NC     := \033[0m # No Color

help: ## Показать это сообщение с помощью
	@echo "$(BLUE)AI Sales Assistant - Makefile команды$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

# ==============================================
# Установка и настройка
# ==============================================

install: ## Установить зависимости через uv
	@echo "$(YELLOW)📦 Установка зависимостей...$(NC)"
	uv sync

install-dev: ## Установить зависимости + dev-пакеты
	@echo "$(YELLOW)📦 Установка зависимостей (включая dev)...$(NC)"
	uv sync --all-extras

install-hooks: ## Установить pre-commit hooks
	@echo "$(YELLOW)🪝 Установка pre-commit hooks...$(NC)"
	uv run pre-commit install

# ==============================================
# Запуск бота
# ==============================================

run: ## Запустить бота
	@echo "$(GREEN)🚀 Запуск AI Sales Assistant...$(NC)"
	uv run python -m src.bot

dev: ## Запустить бота в режиме разработки (с автоперезагрузкой через watchdog - будущее)
	@echo "$(GREEN)🚀 Запуск в dev режиме...$(NC)"
	uv run python -m src.bot

# ==============================================
# База данных и миграции
# ==============================================

migrate: upgrade ## Применить миграции (alias для upgrade)

migrate-create: ## Создать новую миграцию (использование: make migrate-create name=add_field)
	@if [ -z "$(name)" ]; then \
		echo "$(YELLOW)⚠️  Укажите имя миграции: make migrate-create name=имя_миграции$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)📝 Создание миграции: $(name)...$(NC)"
	uv run aerich migrate --name "$(name)"

upgrade: ## Применить все миграции
	@echo "$(YELLOW)⬆️  Применение миграций...$(NC)"
	uv run aerich upgrade

downgrade: ## Откатить последнюю миграцию
	@echo "$(YELLOW)⬇️  Откат миграции...$(NC)"
	uv run aerich downgrade

init-db: ## Инициализировать Aerich (только первый раз)
	@echo "$(YELLOW)🗄️  Инициализация Aerich...$(NC)"
	uv run aerich init -t src.database.config.TORTOISE_ORM
	uv run aerich init-db

# ==============================================
# Проверка кода
# ==============================================

lint: ## Проверить код через Ruff
	@echo "$(YELLOW)🔍 Проверка кода (Ruff)...$(NC)"
	uv run ruff check src/

lint-fix: ## Исправить проблемы автоматически
	@echo "$(YELLOW)🔧 Автоисправление (Ruff)...$(NC)"
	uv run ruff check --fix src/

format: ## Отформатировать код
	@echo "$(YELLOW)✨ Форматирование кода (Ruff)...$(NC)"
	uv run ruff format src/

type-check: ## Проверить типы через MyPy
	@echo "$(YELLOW)🔎 Проверка типов (MyPy)...$(NC)"
	uv run mypy src/

check: lint type-check ## Полная проверка (lint + type-check)
	@echo "$(GREEN)✅ Все проверки пройдены!$(NC)"

# ==============================================
# Тестирование
# ==============================================

test: ## Запустить тесты
	@echo "$(YELLOW)🧪 Запуск тестов...$(NC)"
	uv run pytest tests/ -v

test-cov: ## Запустить тесты с покрытием
	@echo "$(YELLOW)🧪 Запуск тестов с покрытием...$(NC)"
	uv run pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

test-watch: ## Запустить тесты в watch-режиме (будущее)
	@echo "$(YELLOW)🧪 Запуск тестов в watch-режиме...$(NC)"
	uv run pytest-watch tests/ -v

# ==============================================
# Docker
# ==============================================

docker-build: ## Собрать Docker образ
	@echo "$(YELLOW)🐳 Сборка Docker образа...$(NC)"
	docker compose build

docker-up: ## Запустить контейнеры (БД + бот)
	@echo "$(GREEN)🐳 Запуск Docker контейнеров...$(NC)"
	docker compose up -d

docker-down: ## Остановить контейнеры
	@echo "$(YELLOW)🐳 Остановка Docker контейнеров...$(NC)"
	docker compose down

docker-logs: ## Показать логи контейнеров
	@echo "$(BLUE)🐳 Логи Docker контейнеров...$(NC)"
	docker compose logs -f

docker-restart: ## Перезапустить контейнеры
	@echo "$(YELLOW)🐳 Перезапуск Docker контейнеров...$(NC)"
	docker compose restart

docker-shell: ## Войти в shell контейнера бота
	@echo "$(BLUE)🐳 Вход в shell контейнера...$(NC)"
	docker compose exec bot bash

docker-migrate: ## Применить миграции в Docker
	@echo "$(YELLOW)🐳 Применение миграций в Docker...$(NC)"
	docker compose exec bot uv run aerich upgrade

docker-clean: ## Удалить контейнеры и volumes (ОСТОРОЖНО!)
	@echo "$(YELLOW)⚠️  Удаление контейнеров и volumes...$(NC)"
	docker compose down -v

# ==============================================
# Очистка
# ==============================================

clean: ## Очистить временные файлы
	@echo "$(YELLOW)🧹 Очистка временных файлов...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.log" -delete
	rm -rf .pytest_cache .coverage htmlcov/ .mypy_cache .ruff_cache
	@echo "$(GREEN)✅ Очистка завершена!$(NC)"

clean-all: clean docker-clean ## Полная очистка (включая Docker)
	@echo "$(GREEN)✅ Полная очистка завершена!$(NC)"

# ==============================================
# Разработка
# ==============================================

setup: install install-dev install-hooks ## Полная настройка окружения
	@echo "$(GREEN)✅ Окружение настроено!$(NC)"
	@echo "$(BLUE)Теперь создайте .env файл:$(NC)"
	@echo "  cp .env.example .env"
	@echo "$(BLUE)И отредактируйте его с вашими токенами$(NC)"

status: ## Показать статус проекта
	@echo "$(BLUE)📊 Статус проекта:$(NC)"
	@echo ""
	@echo "$(YELLOW)Python:$(NC)"
	@python --version 2>/dev/null || echo "  ❌ Python не найден"
	@echo ""
	@echo "$(YELLOW)uv:$(NC)"
	@uv --version 2>/dev/null || echo "  ❌ uv не установлен"
	@echo ""
	@echo "$(YELLOW)Docker:$(NC)"
	@docker --version 2>/dev/null || echo "  ❌ Docker не установлен"
	@echo ""
	@echo "$(YELLOW)Docker Compose:$(NC)"
	@docker compose version 2>/dev/null || echo "  ❌ Docker Compose не установлен"
	@echo ""
	@echo "$(YELLOW)Pre-commit:$(NC)"
	@uv run pre-commit --version 2>/dev/null || echo "  ❌ Pre-commit не установлен"
	@echo ""
	@echo "$(YELLOW).env файл:$(NC)"
	@if [ -f .env ]; then echo "  ✅ Существует"; else echo "  ❌ Не найден (создайте из .env.example)"; fi
