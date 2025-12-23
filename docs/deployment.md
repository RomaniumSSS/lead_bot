# 🚀 Инструкция по деплою на VPS

Это пошаговая инструкция для деплоя AI Sales Assistant на Ubuntu Server (VPS).

---

## 📋 Требования

- VPS с Ubuntu Server 22.04+ (рекомендуется от 1GB RAM)
- SSH доступ к серверу
- Доменное имя (опционально, для webhook)

---

## 🛠️ Шаг 1: Подключение к VPS

```bash
ssh root@YOUR_VPS_IP
# или
ssh username@YOUR_VPS_IP
```

---

## 🔧 Шаг 2: Установка Docker и Docker Compose

### Обновление системы

```bash
sudo apt update
sudo apt upgrade -y
```

### Установка Docker

```bash
# Установка зависимостей
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common

# Добавление официального GPG ключа Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Добавление репозитория Docker
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установка Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Проверка установки
docker --version
docker compose version
```

### Добавление пользователя в группу docker (чтобы не использовать sudo)

```bash
sudo usermod -aG docker $USER
# Перелогиньтесь для применения изменений
exit
# ssh username@YOUR_VPS_IP снова
```

---

## 📦 Шаг 3: Установка Git и клонирование проекта

```bash
# Установка Git
sudo apt install -y git

# Клонирование репозитория
git clone https://github.com/YOUR_USERNAME/ai-sales-assistant.git
cd ai-sales-assistant
```

**Или**, если нет Git репозитория, загрузите проект через `scp`:

```bash
# На локальной машине:
scp -r /path/to/ai-sales-assistant username@YOUR_VPS_IP:/home/username/
```

---

## ⚙️ Шаг 4: Настройка .env файла

```bash
cd ai-sales-assistant
cp .env.example .env
nano .env
```

Заполните все переменные:

```env
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
ANTHROPIC_API_KEY=YOUR_CLAUDE_API_KEY
DATABASE_URL=postgres://salesbot:salesbot_password@db:5432/sales_assistant
OWNER_TELEGRAM_ID=YOUR_TELEGRAM_ID
BUSINESS_NAME=Ваш Бизнес
BUSINESS_DESCRIPTION=Описание вашего бизнеса
MODE=production
```

Сохраните (`Ctrl+O`, `Enter`, `Ctrl+X`).

---

## 🐳 Шаг 5: Запуск через Docker Compose

```bash
# Запуск БД и бота
docker compose up -d

# Проверка статуса контейнеров
docker compose ps
```

Вы должны увидеть:

```
NAME                     COMMAND                  SERVICE    STATUS
ai-sales-assistant-bot   "uv run python -m sr…"   bot        Up
ai-sales-assistant-db    "docker-entrypoint.s…"   db         Up
```

---

## 🗄️ Шаг 6: Инициализация БД (миграции)

```bash
# Инициализация Aerich (только первый раз)
docker compose exec bot uv run aerich init -t src.database.config.TORTOISE_ORM
docker compose exec bot uv run aerich init-db
```

Если миграции уже есть в проекте:

```bash
docker compose exec bot uv run aerich upgrade
```

---

## 📊 Шаг 7: Проверка логов

```bash
# Просмотр логов бота
docker compose logs -f bot

# Просмотр логов БД
docker compose logs -f db
```

Если всё ОК, вы увидите:

```
✅ База данных подключена
✅ Бот запущен! Ожидание сообщений...
```

---

## ✅ Шаг 8: Проверка работы

1. Откройте Telegram и найдите вашего бота.
2. Отправьте `/start`.
3. Бот должен ответить приветствием.
4. Отправьте владельцу команду `/stats` — должна прийти статистика.

---

## 🔄 Обновление проекта

Если вы обновили код на GitHub:

```bash
cd ai-sales-assistant

# Остановить контейнеры
docker compose down

# Получить изменения
git pull

# Пересобрать и запустить
docker compose up -d --build

# Применить миграции (если были изменения в моделях)
docker compose exec bot uv run aerich upgrade
```

---

## 🔗 Шаг 9 (опционально): Настройка Webhook для продакшена

Webhook — более эффективный режим работы для продакшена. Вместо того, чтобы бот опрашивал Telegram каждые несколько секунд (polling), Telegram сам отправляет обновления на ваш сервер.

### Преимущества webhook:
- ⚡ Мгновенная доставка сообщений (без задержки)
- 💰 Меньше нагрузка на сервер
- 🚀 Лучше масштабируется

### Требования:
- Доменное имя (например, `yourdomain.com`)
- HTTPS (SSL сертификат)
- Открытый порт 8080 (или другой)

---

### 9.1. Получение доменного имени

Зарегистрируйте домен (например, на [Namecheap](https://www.namecheap.com/) или [Cloudflare](https://www.cloudflare.com/)).

Укажите A-запись в DNS:
```
A    @    YOUR_VPS_IP
```

Проверьте:
```bash
ping yourdomain.com
# Должен вернуть ваш VPS IP
```

---

### 9.2. Установка Nginx

```bash
sudo apt install -y nginx
sudo systemctl start nginx
sudo systemctl enable nginx
```

Проверьте, что Nginx работает:
```bash
curl http://yourdomain.com
# Должна вернуться дефолтная страница Nginx
```

---

### 9.3. Установка SSL (Let's Encrypt)

```bash
# Установка Certbot
sudo apt install -y certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d yourdomain.com

# Certbot автоматически настроит Nginx для HTTPS
```

Проверьте:
```bash
curl https://yourdomain.com
# Должна вернуться дефолтная страница Nginx через HTTPS
```

---

### 9.4. Настройка Nginx для проксирования webhook

Создайте конфиг Nginx:

```bash
sudo nano /etc/nginx/sites-available/ai-sales-assistant
```

Вставьте:

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    # SSL certificates (Certbot автоматически добавит)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Webhook endpoint
    location /webhook {
        proxy_pass http://localhost:8080/webhook;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Healthcheck endpoint (опционально)
    location /health {
        proxy_pass http://localhost:8080/health;
        proxy_http_version 1.1;
    }
}
```

Активируйте конфиг:

```bash
sudo ln -s /etc/nginx/sites-available/ai-sales-assistant /etc/nginx/sites-enabled/
sudo nginx -t  # Проверка конфигурации
sudo systemctl restart nginx
```

---

### 9.5. Обновление .env для webhook

```bash
cd ai-sales-assistant
nano .env
```

Добавьте/измените:

```env
BOT_MODE=webhook
WEBHOOK_URL=https://yourdomain.com/webhook
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8080
```

Сохраните (`Ctrl+O`, `Enter`, `Ctrl+X`).

---

### 9.6. Перезапуск бота

```bash
docker compose down
docker compose up -d --build
```

Проверьте логи:

```bash
docker compose logs -f bot
```

Вы должны увидеть:

```
🔗 Режим работы: WEBHOOK
🔗 Настройка webhook: https://yourdomain.com/webhook
✅ Webhook URL установлен в Telegram
✅ Webhook сервер запущен на порту 8080
✅ Бот запущен в режиме webhook! Ожидание обновлений...
```

---

### 9.7. Проверка работы webhook

Отправьте сообщение боту в Telegram. Если всё настроено правильно, бот ответит мгновенно.

Проверить статус webhook можно через Telegram Bot API:

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

Ответ должен содержать:
```json
{
  "ok": true,
  "result": {
    "url": "https://yourdomain.com/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0,
    "max_connections": 40
  }
}
```

---

### 9.8. Возврат к polling режиму

Если webhook не работает или нужно вернуться к polling:

```bash
# В .env
BOT_MODE=polling

# Перезапуск
docker compose down
docker compose up -d --build
```

Бот автоматически удалит webhook и вернётся к polling.

---

## 🛡️ Безопасность (рекомендации)

### 1. Firewall (UFW)

Откройте только нужные порты:

```bash
sudo ufw allow 22/tcp     # SSH
sudo ufw allow 80/tcp     # HTTP (если будете использовать webhook)
sudo ufw allow 443/tcp    # HTTPS (для webhook)
sudo ufw enable
sudo ufw status
```

### 2. Регулярные обновления

```bash
sudo apt update && sudo apt upgrade -y
```

### 3. Ограничение доступа к PostgreSQL

По умолчанию PostgreSQL в Docker доступен только из Docker сети. Не открывайте порт 5432 наружу.

---

## 🔧 Полезные команды

### Остановка бота

```bash
docker compose stop
```

### Перезапуск бота

```bash
docker compose restart bot
```

### Просмотр логов в файле

```bash
docker compose exec bot cat /app/logs/bot.log
```

### Вход в контейнер бота (для отладки)

```bash
docker compose exec bot bash
```

### Удаление всех контейнеров и данных (ОСТОРОЖНО!)

```bash
docker compose down -v  # -v удаляет volumes (БД будет удалена!)
```

---

## 🌐 Webhook вместо Polling (опционально, для продакшена)

Polling (текущий режим) подходит для MVP, но для production рекомендуется webhook.

### Требования:
- Доменное имя (например, `bot.yourdomain.com`)
- SSL сертификат (Let's Encrypt через Certbot)

### Настройка webhook:

1. Установите Nginx и Certbot.
2. Настройте reverse proxy Nginx → бот.
3. Измените код бота для работы с webhook (вместо polling).

**Это тема для отдельного гайда.** На MVP используйте polling.

---

## 📞 Troubleshooting

### Проблема: "Cannot connect to database"

**Решение:**
- Проверьте, запущен ли контейнер БД: `docker compose ps`
- Проверьте логи БД: `docker compose logs db`
- Убедитесь, что `DATABASE_URL` в `.env` правильный.

### Проблема: "Bot token is invalid"

**Решение:**
- Проверьте `TELEGRAM_BOT_TOKEN` в `.env`.
- Убедитесь, что токен активен (проверьте через @BotFather).

### Проблема: "Anthropic API error"

**Решение:**
- Проверьте `ANTHROPIC_API_KEY` в `.env`.
- Убедитесь, что у вас есть кредиты на аккаунте Anthropic.
- Проверьте логи: `docker compose logs -f bot`.

---

## 🎉 Готово!

Ваш AI Sales Assistant работает 24/7 на VPS! 🚀

Если нужна помощь — напишите в поддержку или создайте issue на GitHub.

---

**Документ актуален**: 21.12.2025
