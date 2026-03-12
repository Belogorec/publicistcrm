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
cd projectpress/projectpress_crm
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

## Railway деплой как второй сервис

1. В Railway проекте `projectpress` нажмите `New Service` -> `GitHub Repo`.
2. Выберите репозиторий CRM (когда заполните `Belogorec/publicistcrm`).
3. Для сервиса задайте root directory: `projectpress_crm` (если монорепо) или `/` (если CRM отдельным репо).
4. Добавьте env:
   - `CRM_INGEST_API_KEY=<секрет>`
   - `CRM_DB_PATH=/data/projectpress_crm.db`
5. Добавьте volume и смонтируйте в `/data`.
6. Deploy.
7. Вкладка `Settings -> Networking -> Domains`:
   - Добавьте домен вида `crm.<ваш-домен-проекта>`
   - Пропишите DNS CNAME по инструкции Railway.

После публикации домена укажите в боте:

- `CRM_API_URL=https://crm.<ваш-домен-проекта>/api/events`
- `CRM_API_KEY=<тот же CRM_INGEST_API_KEY>`
