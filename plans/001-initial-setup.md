# План 001: Инициализация проекта AI Sales Assistant

## Objective (Цель)
Создать базовую структуру проекта AI Sales Assistant для малого бизнеса с Telegram-ботом, настроить окружение разработки, документацию и подготовить к деплою на VPS.

## Context (Контекст)
- Проект с нуля, пустая директория
- За основу берём структуру из health-management-bot
- Нужна полная документация (docs/, AGENTS.md)
- Подготовка к работе на сервере через Docker

## Proposed Steps (Предлагаемые шаги)

### Фаза 1: Документация и Архитектура (Documentation-First)
1. **Создать AGENTS.md** — инструкции для AI-агентов (адаптировать под Sales Assistant)
2. **Создать docs/product.md** — описание продукта, User Flow, бизнес-логика
3. **Создать docs/tech.md** — техническая архитектура, стек, структура проекта

### Фаза 2: Инфраструктура и Окружение
4. **Создать pyproject.toml** — управление зависимостями (uv)
   - aiogram 3.x
   - anthropic (Claude API)
   - tortoise-orm
   - asyncpg (PostgreSQL async driver)
   - aerich (миграции)
   - python-dotenv
   
5. **Создать docker-compose.yml** — PostgreSQL + бот (для разработки и продакшена)

6. **Создать .env.example** — шаблон переменных окружения:
   - TELEGRAM_BOT_TOKEN
   - ANTHROPIC_API_KEY
   - DATABASE_URL
   - OWNER_TELEGRAM_ID

7. **Создать .gitignore** — исключить .env, __pycache__, db.sqlite3, и т.д.

8. **Создать .python-version** — 3.11

### Фаза 3: Структура Кода
9. **Создать структуру директорий:**
```
src/
├── __init__.py
├── main.py              # Точка входа
├── config.py            # Загрузка настроек из .env
├── models/              # Tortoise ORM модели
│   ├── __init__.py
│   ├── lead.py          # Модель лида
│   └── conversation.py  # История диалогов
├── handlers/            # Telegram handlers
│   ├── __init__.py
│   ├── start.py         # /start команда
│   └── conversation.py  # Обработка сообщений лида
├── services/            # Бизнес-логика
│   ├── __init__.py
│   ├── llm.py           # Интеграция с Claude
│   ├── qualifier.py     # Квалификация лидов
│   └── scheduler.py     # Follow-up и напоминания
└── utils/
    ├── __init__.py
    └── logger.py        # Логирование
```

10. **Создать базовые модели данных:**
    - Lead (id, telegram_id, username, first_name, status, budget, task, deadline, created_at)
    - Conversation (id, lead_id, message, role, timestamp)

11. **Создать src/config.py** — загрузка переменных окружения

12. **Создать src/main.py** — минимальный рабочий бот (просто эхо)

### Фаза 4: Миграции и README
13. **Настроить Aerich** — pyproject.toml конфигурация для миграций

14. **Создать README.md** — инструкции по запуску:
    - Установка зависимостей (uv sync)
    - Настройка .env
    - Запуск через Docker
    - Применение миграций

15. **Создать Dockerfile** (если понадобится для VPS)

## Risks (Риски)

1. **Tortoise ORM + asyncpg + PostgreSQL** — могут быть проблемы с настройкой connection pool.
   - Митигация: использовать проверенную конфигурацию из примера.

2. **Anthropic API rate limits** — Claude может иметь лимиты на запросы.
   - Митигация: добавить обработку ошибок 429, exponential backoff.

3. **VPS настройка** — пользователь слабо разбирается в серверах.
   - Митигация: создать максимально простой docker-compose для деплоя.

4. **Кириллица в пути проекта** — `/Users/ramanpazharytski/обработка лидов/` может вызвать проблемы в некоторых инструментах.
   - Митигация: использовать абсолютные пути, тестировать на UTF-8.

## Rollback Strategy (Стратегия отката)

Если что-то пойдёт не так на этапе инициализации:
- Все файлы можно безопасно удалить (проект пустой).
- Docker контейнеры можно остановить и удалить через `docker-compose down -v`.
- Git не инициализирован — нет риска потери данных.

## Success Criteria (Критерии успеха)

✅ Документация создана и актуальна (AGENTS.md, docs/product.md, docs/tech.md)
✅ Структура проекта соответствует best practices
✅ Бот запускается локально и отвечает на /start
✅ PostgreSQL подключается через docker-compose
✅ Миграции настроены (Aerich)
✅ README содержит чёткие инструкции по запуску
✅ .env.example заполнен всеми необходимыми переменными

## Next Steps (Следующие шаги после этого плана)

После успешной инициализации следующим планом будет:
- **002-lead-qualification.md** — реализация квалификации лидов через Claude
- **003-conversation-flow.md** — диалоговая логика с персонализацией
- **004-scheduling.md** — назначение встреч и follow-up

---

**Ожидаю подтверждения для начала реализации.**

