#!/bin/bash
# Автоматический коммит с генерацией сообщения через OpenCommit

set -e

# Проверяем, что есть изменения для коммита
if ! git diff --cached --quiet; then
    echo "🤖 Генерирую commit message через Claude..."

    # Генерируем сообщение через OpenCommit и сохраняем в файл
    COMMIT_MSG=$(npx opencommit 2>&1 | grep -A1 "Generated commit message:" | tail -n1 | sed 's/^[─—]*$//' | xargs)

    if [ -z "$COMMIT_MSG" ]; then
        echo "❌ Не удалось сгенерировать commit message"
        exit 1
    fi

    echo "📝 Commit message: $COMMIT_MSG"
    echo ""

    # Делаем коммит с сгенерированным сообщением
    git commit -m "$COMMIT_MSG"

    echo "✅ Коммит создан успешно!"
else
    echo "⚠️  Нет изменений для коммита (используйте 'git add' сначала)"
    exit 1
fi

# Test auto-commit
