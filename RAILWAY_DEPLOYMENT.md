# Railway Deployment Guide

## Структура проекта

Это монорепо с двумя сервисами:
- `projectpress/` — Telegram бот на Flask (port 5000)
- `projectpress/projectpress_crm/` — CRM на Flask (port 5002)

## Подготовка

✅ Git репозиторий инициализирован
✅ requirements.txt и Procfile готовы
✅ .env в .gitignore (чувствительные данные не будут закоммичены)

## Деплой на Railway

### Вариант 1: GitHub интеграция (рекомендуется)

1. **Создать GitHub репозиторий** и пушить туда:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/projectpress.git
   git branch -M main
   git push -u origin main
   ```

2. **Настроить Railway**:
   - Перейти на railway.app
   - Log in or Sign up
   - Create New Project
   - Choose "Deploy from GitHub"
   - Connect GitHub аккаунт
   - Select репозиторий `projectpress`

### Вариант 2: Текущий git репозиторий (локальный)

Railway может работать с локальным git. Но сначала нужно убедиться что репо готово.

## Специфика для двух сервисов

### Сервис 1: Telegram Bot (projectpress/)

```
Root dir: projectpress/
Procfile: web: gunicorn flask_app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
Build cmd: pip install -r requirements.txt
Environment variables:
  - BOT_TOKEN
  - WEBHOOK_SECRET
  - CRM_API_URL=https://your-crm.railway.app
  - Остальные из .env
```

### Сервис 2: CRM (projectpress/projectpress_crm/)

```
Root dir: projectpress/projectpress_crm/
Procfile: web: gunicorn flask_app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
Build cmd: pip install -r requirements.txt
Environment variables:
  - SESSION_SECRET_KEY
  - ADMIN_IDS
  - BOT_TOKEN
  - CRM_INGEST_API_KEY
  - Все остальные из .env
```

## Environment Variables для Railway

Bot сервис:
```
BOT_TOKEN=...
WEBHOOK_SECRET=...
CRM_API_URL=https://your-crm-service.railway.app
FILE_STORAGE_ROOT=/data
```

CRM сервис:
```
SESSION_SECRET_KEY=your-strong-random-secret-min-32-chars
AUTH_TOKEN_LIFETIME=86400
ADMIN_IDS=your_telegram_id
BOT_TOKEN=...
CRM_INGEST_API_KEY=...
CRM_DB_PATH=/data/projectpress_crm.db
CRM_DEFAULT_MANAGER=
```

## Решение: One Project, Two Services

На Railway можно создать один Project с двумя Services:

1. **Railway Project**: projectpress
2. **Service 1**: Bot (из папки projectpress/)
3. **Service 2**: CRM (из папки projectpress/projectpress_crm/)

Railway автоматически получит доступ к обоим и сможет их развернуть.

## Шаги в Railway UI

1. Создать Project
2. Add Service → GitHub
3. Deploy Bot (выбрать projectpress/flask_app.py)
4. Add Service → GitHub  
5. Deploy CRM (выбрать projectpress/projectpress_crm/flask_app.py)
6. Оба получат уникальные URL вроде:
   - Bot: bot-service.railway.app
   - CRM: crm-service.railway.app

## Важные заметки

- Railway автоматически определяет Procfile в корне сервиса
- Если Procfile находится в подпапке, нужно указать в Railway UI
- Каждый сервис получает собственный DATABASE_URL и переменные окружения
- Логи доступны в Railway Dashboard

## Быстрый старт

Если у вас уже есть Railway аккаунт:

```bash
# 1. Убедиться что все в git
cd /Users/maks/Documents/code\ vs
git status

# 2. Если нужно, пушить на GitHub
git remote add origin https://github.com/your-username/projectpress.git
git push -u origin main

# 3. На railway.app создать новый проект из GitHub репо
# 4. Railway автоматически найдет оба Procfile и развернет оба сервиса
```

## Проблемы?

Если сервис не запускается:
- Проверить logs в Railway Dashboard
- Убедиться что все ENV переменные установлены
- Проверить что requirements.txt содержит все зависимости
- Убедиться что Procfile указан корректно (может быть в подпапке)
