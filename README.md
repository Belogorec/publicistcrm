# ProjectPress CRM

Отдельный CRM-сервис для проекта `projectpress`.

## Границы проекта

Этот репозиторий относится только к `Belogorec/publicistcrm`.

Локально рядом могут лежать другие отдельные репозитории:
- `luchbarbot`
- `luchbarbot-relay`
- `projectpress`
- вложенная папка `publicistcrm`

Они не считаются частью этого репозитория и добавлены в корневой `.gitignore`, чтобы рабочее пространство не смешивало `ProjectPress` и `ЛУЧ`.

## Production

- Railway CRM для `projectpress` разворачивается из `Belogorec/publicistcrm`.
- Root directory в Railway: корень репозитория.
- База обычно хранится во внешнем volume, например `/data/projectpress_crm.db`.

## CRM auth

- Корень `/` закрыт авторизацией и без активной сессии ведет на `/login`.
- Вход выполнен по обычной паре логин/пароль.
- Текущие дефолтные данные входа: `admin / 74952870022`.
- При необходимости можно переопределить через `CRM_LOGIN`, `CRM_PASSWORD`, `AUTH_SESSION_LIFETIME`.
- Нужные переменные: `SESSION_SECRET_KEY`, `CRM_INGEST_API_KEY`, `CRM_DB_PATH`.
- Старый Telegram login flow вынесен в `archive/telegram_auth/`.

## Что уже реализовано

- API приёма событий из бота: `POST /api/events`
- CRM-сущности:
  - `clients`
  - `applications`
  - `application_revisions`
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
cp .env.example .env
python init_db.py
python flask_app.py
```

Проверка:

```bash
curl -s http://localhost:5002/health
```

## API

### POST `/api/events`

Опциональный заголовок:
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
    "agreed_price": 7000
  },
  "meta": {
    "actor_tg_id": "777",
    "comment": "manual moderation"
  }
}
```

## Railway

1. Откройте проект `projectpress` в Railway.
2. Создайте сервис из `Belogorec/publicistcrm`.
3. Подключите volume с mount path `/data`.
4. Добавьте переменные:
   - `CRM_INGEST_API_KEY`
   - `CRM_DB_PATH=/data/projectpress_crm.db`
5. В боте `projectpress` укажите:
   - `CRM_API_URL=https://crm.<ваш-домен>/api/events`
   - `CRM_API_KEY=<тот же CRM_INGEST_API_KEY>`
   - `CRM_SYNC_TIMEOUT=8`
