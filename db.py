import os
import sqlite3

from config import CRM_DB_PATH


STATUS_GROUPS = {
    "Новая заявка": "incoming",
    "На первичной проверке": "incoming",
    "Требует уточнения": "incoming",
    "Возвращена на доработку клиенту": "incoming",
    "На рассмотрении редакции": "approval",
    "Одобрена": "approval",
    "Отклонена": "approval",
    "Ожидает счет / договор": "commercial",
    "Ожидает оплату": "commercial",
    "Частично оплачена": "commercial",
    "Оплачена": "commercial",
    "В работе": "production",
    "Материал получен": "production",
    "На публикации": "production",
    "Опубликовано": "production",
    "Закрыто": "production",
    "Отменено клиентом": "service",
    "Архив": "service",
    "Спор / проблемная заявка": "service",
}


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(CRM_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(CRM_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def run_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id     TEXT UNIQUE,
            username        TEXT,
            full_name       TEXT,
            role            TEXT NOT NULL DEFAULT 'manager',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS clients (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id         TEXT NOT NULL UNIQUE,
            telegram_username   TEXT,
            name                TEXT,
            phone               TEXT,
            email               TEXT,
            company             TEXT,
            inn                 TEXT,
            client_type         TEXT,
            source              TEXT,
            manager_id          INTEGER REFERENCES users(id),
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS applications (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            external_lead_id        INTEGER NOT NULL UNIQUE,
            client_id               INTEGER NOT NULL REFERENCES clients(id),
            title                   TEXT,
            media                   TEXT,
            placement_format        TEXT,
            urgency                 TEXT,
            amount                  INTEGER,
            payment_status          TEXT NOT NULL DEFAULT 'не выставлено',
            deadline_at             TEXT,
            status                  TEXT NOT NULL DEFAULT 'Новая заявка',
            status_group            TEXT NOT NULL DEFAULT 'incoming',
            responsible_manager_id  INTEGER REFERENCES users(id),
            archived                INTEGER NOT NULL DEFAULT 0,
            created_at              TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS application_revisions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id      INTEGER NOT NULL REFERENCES applications(id),
            iteration           INTEGER NOT NULL,
            source_event        TEXT NOT NULL,
            payload_json        TEXT NOT NULL,
            changed_by          TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(application_id, iteration)
        );

        CREATE TABLE IF NOT EXISTS status_history (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id      INTEGER NOT NULL REFERENCES applications(id),
            old_status          TEXT,
            new_status          TEXT NOT NULL,
            changed_by          TEXT,
            comment             TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS comments (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id      INTEGER NOT NULL REFERENCES applications(id),
            source              TEXT NOT NULL,
            source_id           TEXT,
            is_internal         INTEGER NOT NULL DEFAULT 1,
            text                TEXT,
            author_telegram_id  TEXT,
            created_at          TEXT NOT NULL,
            UNIQUE(source, source_id)
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id      INTEGER NOT NULL REFERENCES applications(id),
            revision_id         INTEGER REFERENCES application_revisions(id),
            source              TEXT NOT NULL,
            source_file_id      TEXT,
            category            TEXT,
            filename            TEXT,
            mime_type           TEXT,
            storage_url         TEXT,
            uploaded_by         TEXT,
            created_at          TEXT NOT NULL,
            UNIQUE(source, source_file_id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id          INTEGER NOT NULL REFERENCES applications(id),
            order_number            TEXT UNIQUE,
            amount                  INTEGER,
            vat_mode                TEXT,
            execution_status        TEXT NOT NULL DEFAULT 'В работе',
            payment_status          TEXT NOT NULL DEFAULT 'не выставлено',
            documents_status        TEXT NOT NULL DEFAULT 'created',
            deadline_at             TEXT,
            responsible_manager_id  INTEGER REFERENCES users(id),
            created_at              TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS payments (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id                INTEGER REFERENCES orders(id),
            application_id          INTEGER NOT NULL REFERENCES applications(id),
            amount                  INTEGER NOT NULL,
            currency                TEXT NOT NULL DEFAULT 'RUB',
            status                  TEXT NOT NULL,
            provider_payment_id     TEXT,
            payment_method          TEXT,
            comment                 TEXT,
            paid_at                 TEXT,
            created_at              TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS documents (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id                INTEGER REFERENCES orders(id),
            application_id          INTEGER NOT NULL REFERENCES applications(id),
            doc_type                TEXT NOT NULL,
            doc_number              TEXT,
            version                 INTEGER NOT NULL DEFAULT 1,
            status                  TEXT NOT NULL DEFAULT 'created',
            storage_url             TEXT,
            created_at              TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(order_id, doc_type, version)
        );

        CREATE TABLE IF NOT EXISTS event_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name          TEXT NOT NULL,
            source              TEXT NOT NULL,
            payload_json        TEXT NOT NULL,
            processed_ok        INTEGER NOT NULL DEFAULT 1,
            error_text          TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
        CREATE INDEX IF NOT EXISTS idx_applications_client ON applications(client_id);
        CREATE INDEX IF NOT EXISTS idx_status_history_app ON status_history(application_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_comments_app ON comments(application_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_attachments_app ON attachments(application_id, created_at);

        CREATE TABLE IF NOT EXISTS auth_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL UNIQUE,
            telegram_id     TEXT NOT NULL,
            username        TEXT,
            full_name       TEXT,
            expires_at      TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS auth_codes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            code            TEXT NOT NULL UNIQUE,
            telegram_id     TEXT,
            confirmed       INTEGER NOT NULL DEFAULT 0,
            expires_at      TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_auth_sessions_session_id ON auth_sessions(session_id);
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_telegram_id ON auth_sessions(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_auth_codes_code ON auth_codes(code);
        CREATE INDEX IF NOT EXISTS idx_auth_codes_telegram_id ON auth_codes(telegram_id);
        """
    )
    conn.commit()
