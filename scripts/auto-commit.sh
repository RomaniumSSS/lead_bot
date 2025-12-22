#!/bin/bash
# Автоматический git commit с генерацией сообщения через OpenCommit (Claude Haiku)
#
# Использование:
#   ./scripts/auto-commit.sh
#   или добавь alias: alias gc="./scripts/auto-commit.sh"

set -e

# Проверяем, что есть staged изменения
if git diff --cached --quiet; then
    echo "⚠️  Нет staged изменений для коммита."
    echo "💡 Используйте 'git add <файлы>' сначала"
    exit 1
fi

echo "🤖 Генерирую commit message через Claude Haiku..."

# Генерируем commit message через OpenCommit и парсим вывод
OUTPUT=$(npx opencommit 2>&1 || true)

# Извлекаем сгенерированное сообщение
COMMIT_MSG=$(echo "$OUTPUT" | grep -A 1 "Generated commit message:" | tail -n 1 | sed 's/^[─—-]*$//' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')

# Проверяем, что сообщение получено
if [ -z "$COMMIT_MSG" ] || [ "$COMMIT_MSG" = "——————————————————" ]; then
    echo "❌ Не удалось сгенерировать commit message"
    echo ""
    echo "📋 Вывод OpenCommit:"
    echo "$OUTPUT"
    exit 1
fi

echo "📝 Commit message:"
echo "   $COMMIT_MSG"
echo ""

# Делаем коммит с сгенерированным сообщением
git commit -m "$COMMIT_MSG"

echo ""
echo "✅ Коммит успешно создан!"
