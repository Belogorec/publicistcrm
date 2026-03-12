# ProjectPress CRM (Railway service)

Отдельный CRM-сервис для обработки событий из Telegram-бота `projectpress`.

## Что уже реализовано

- API приёма событий из бота: `POST /api/events`
- Базовая модель CRM-сущностей:
  - `clients`
  - `applications`
  - `application_revisions` (версии заявки)
  - `status_history`
  - `comments`
  - `attachments`
  - `orders`
  - `payments`
  - `documents`
  - `event_log`
- Автосоздание `order` при статусе `Одобрена`
- Хранение полной JSON-версии заявки на каждое событие

## Локальный запуск

```bash
git clone https://github.com/Belogorec/publicistcrm.git
cd publicistcrm
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # вставьте свои ключи
python init_db.py
python flask_app.py
```

Проверка:

```bash
curl -s http://localhost:5002/health
```

## API

### POST `/api/events`

Заголовок (опционально, если задан env):

- `X-CRM-API-Key: <CRM_INGEST_API_KEY>`

Пример payload:

```json
{
  "event": "lead.status_changed",
  "source": "projectpress_bot",
  "lead": {
    "id": 42,
    "tg_id": "123456789",
    "tg_username": "client",
    "tg_name": "Client Name",
    "status": "under_review",
    "selected_media": "journal_1",
    "selected_format": "standard_post",
    "agreed_price": 7000,
    "messages": [],
    "files": [],
    "moderation": []
  },
  "meta": {
    "actor_tg_id": "777",
    "comment": "manual moderation"
  }
}
```

## Railway деплой

Репозиторий https://github.com/Belogorec/publicistcrm

### 1. Создание сервиса

1. В Railway откройте проект `projectpress`.
2. Нажмите **New Service → GitHub Repo**.
3. Выберите `Belogorec/publicistcrm`.
4. Root directory: оставить пустым (корень репозитория).
5. Start command определяется Procfile автоматически.

### 2. Volume для БД

1. В сервисе CRM откройте вкладку **Volumes**.
2. Создайте volume, mount path: `/data`.

### 3. Environment variables (в Railway Variables)

| Имя                  | Значение                                    |
|----------------------|---------------------------------------------|
| `CRM_INGEST_API_KEY` | секретная строка, которую выставили в боте  |
| `CRM_DB_PATH`        | `/data/projectpress_crm.db`                 |

### 4. Домен

1. Вкладка **Settings → Networking → Domains**.
2. Добавьте `crm.<ваш-домен>` → Railway CNAME.

### 5. Переменные в боте Projectpress

Откройте сервис `projectpress` в Railway → Variables:

| Имя                | Значение                                              |
|--------------------|-------------------------------------------------------|
| `CRM_API_URL`      | `https://crm.<ваш-домен>/api/events`                  |
| `CRM_API_KEY`      | тот же `CRM_INGEST_API_KEY` из сервиса CRM            |
| `CRM_SYNC_TIMEOUT` | `8`                                                   |
