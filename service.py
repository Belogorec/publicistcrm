import json
from typing import Any
from typing import Optional

from db import STATUS_GROUPS


BOT_TO_CRM_STATUS = {
    "new": "Новая заявка",
    "browsing_formats": "На первичной проверке",
    "selected_format": "На первичной проверке",
    "awaiting_material": "Требует уточнения",
    "under_review": "На рассмотрении редакции",
    "approved": "Одобрена",
    "rejected": "Отклонена",
    "needs_clarification": "Возвращена на доработку клиенту",
}


def _crm_status(bot_status: str) -> str:
    return BOT_TO_CRM_STATUS.get(bot_status or "", "Новая заявка")


def _status_group(crm_status: str) -> str:
    return STATUS_GROUPS.get(crm_status, "incoming")


def _next_iteration(conn, application_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(iteration), 0) + 1 AS n FROM application_revisions WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    return int((row or {"n": 1})["n"])


def _ensure_order(conn, application_id: int, amount: Optional[int], manager_id: Optional[int]) -> None:
    row = conn.execute(
        "SELECT id FROM orders WHERE application_id = ?",
        (application_id,),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE orders
            SET amount = COALESCE(?, amount),
                payment_status = 'ожидает оплату',
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (amount, row["id"]),
        )
        return

    conn.execute(
        """
        INSERT INTO orders (
            application_id, order_number, amount, payment_status, responsible_manager_id
        ) VALUES (?, ?, ?, 'ожидает оплату', ?)
        """,
        (application_id, f"PP-{application_id}", amount, manager_id),
    )


def ingest_event(conn, payload: dict[str, Any]) -> dict[str, Any]:
    event_name = (payload.get("event") or "").strip()
    source = (payload.get("source") or "projectpress_bot").strip() or "projectpress_bot"
    lead = payload.get("lead") or {}
    files = lead.get("files") or []
    messages = lead.get("messages") or []
    moderation = lead.get("moderation") or []
    actor = str((payload.get("meta") or {}).get("actor_tg_id") or "") or None

    if not event_name:
        raise ValueError("event is required")
    if not lead.get("tg_id"):
        raise ValueError("lead.tg_id is required")
    if lead.get("id") is None:
        raise ValueError("lead.id is required")

    conn.execute(
        """
        INSERT INTO clients (telegram_id, telegram_username, name, source, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(telegram_id) DO UPDATE SET
            telegram_username = excluded.telegram_username,
            name = excluded.name,
            source = excluded.source,
            updated_at = datetime('now')
        """,
        (
            str(lead.get("tg_id") or ""),
            lead.get("tg_username"),
            lead.get("tg_name"),
            source,
        ),
    )

    client = conn.execute(
        "SELECT id FROM clients WHERE telegram_id = ?",
        (str(lead.get("tg_id") or ""),),
    ).fetchone()

    crm_status = _crm_status(lead.get("status") or "")
    status_group = _status_group(crm_status)

    conn.execute(
        """
        INSERT INTO applications (
            external_lead_id, client_id, title, media, placement_format, amount,
            status, status_group, archived, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(external_lead_id) DO UPDATE SET
            client_id = excluded.client_id,
            title = excluded.title,
            media = excluded.media,
            placement_format = excluded.placement_format,
            amount = excluded.amount,
            status = excluded.status,
            status_group = excluded.status_group,
            archived = excluded.archived,
            updated_at = datetime('now')
        """,
        (
            int(lead.get("id")),
            client["id"],
            lead.get("title") or lead.get("selected_format"),
            lead.get("selected_media"),
            lead.get("selected_format"),
            lead.get("agreed_price"),
            crm_status,
            status_group,
            1 if crm_status in ("Отклонена", "Архив", "Отменено клиентом", "Закрыто") else 0,
        ),
    )

    app_row = conn.execute(
        "SELECT id, status, responsible_manager_id FROM applications WHERE external_lead_id = ?",
        (int(lead.get("id")),),
    ).fetchone()
    application_id = int(app_row["id"])

    prev_status = app_row["status"]
    if prev_status != crm_status:
        conn.execute(
            """
            INSERT INTO status_history (application_id, old_status, new_status, changed_by, comment)
            VALUES (?, ?, ?, ?, ?)
            """,
            (application_id, prev_status, crm_status, actor, (payload.get("meta") or {}).get("comment")),
        )

    iteration = _next_iteration(conn, application_id)
    conn.execute(
        """
        INSERT INTO application_revisions (application_id, iteration, source_event, payload_json, changed_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        (application_id, iteration, event_name, json.dumps(payload, ensure_ascii=False), actor),
    )
    revision_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    for message in messages:
        source_id = str(message.get("id") or "")
        if not source_id:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO comments (
                application_id, source, source_id, is_internal, text, author_telegram_id, created_at
            ) VALUES (?, 'lead_message', ?, 0, ?, ?, COALESCE(?, datetime('now')))
            """,
            (
                application_id,
                source_id,
                message.get("text"),
                str(lead.get("tg_id") or ""),
                message.get("created_at"),
            ),
        )

    for row in moderation:
        source_id = str(row.get("id") or "")
        if not source_id:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO comments (
                application_id, source, source_id, is_internal, text, author_telegram_id, created_at
            ) VALUES (?, 'moderation', ?, 1, ?, ?, COALESCE(?, datetime('now')))
            """,
            (
                application_id,
                source_id,
                row.get("comment") or row.get("action"),
                row.get("admin_tg_id"),
                row.get("created_at"),
            ),
        )

    for f in files:
        source_file_id = str(f.get("tg_file_id") or f.get("id") or "")
        if not source_file_id:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO attachments (
                application_id, revision_id, source, source_file_id, category,
                filename, mime_type, storage_url, uploaded_by, created_at
            ) VALUES (?, ?, 'lead_file', ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))
            """,
            (
                application_id,
                revision_id,
                f.get("file_type"),
                f.get("original_filename"),
                f.get("mime_type"),
                f.get("storage_path"),
                str(lead.get("tg_id") or ""),
                f.get("created_at"),
            ),
        )

    if crm_status == "Одобрена":
        _ensure_order(conn, application_id, lead.get("agreed_price"), app_row["responsible_manager_id"])

    conn.execute(
        """
        INSERT INTO event_log (event_name, source, payload_json, processed_ok)
        VALUES (?, ?, ?, 1)
        """,
        (event_name, source, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()

    return {
        "ok": True,
        "application_id": application_id,
        "revision": iteration,
        "status": crm_status,
    }
