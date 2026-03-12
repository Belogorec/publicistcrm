import traceback

import requests
from flask import Flask, Response, abort, redirect, render_template, request, url_for

from config import BOT_TOKEN, CRM_INGEST_API_KEY
from db import STATUS_GROUPS, connect, run_migrations
from service import add_crm_comment, change_status, get_client_telegram_id, ingest_event
from telegram_notify import send_to_client, status_change_text

ALL_STATUSES = list(STATUS_GROUPS.keys())

app = Flask(__name__)


def bootstrap_schema() -> None:
    conn = connect()
    try:
        run_migrations(conn)
    finally:
        conn.close()


bootstrap_schema()


def _safe_int(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@app.route("/health", methods=["GET"])
def health() -> tuple[dict, int]:
    return {"status": "ok"}, 200


@app.route("/", methods=["GET"])
def applications_list():
    status = (request.args.get("status") or "").strip()
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()
    client_q = (request.args.get("client") or "").strip()
    media_q = (request.args.get("media") or "").strip()
    manager_id = _safe_int((request.args.get("manager_id") or "").strip())
    payment_status = (request.args.get("payment_status") or "").strip()
    archived = (request.args.get("archived") or "").strip()
    q = (request.args.get("q") or "").strip()

    where = []
    params = []

    if status:
        where.append("a.status = ?")
        params.append(status)
    if date_from:
        where.append("datetime(a.created_at) >= datetime(?)")
        params.append(date_from + " 00:00:00")
    if date_to:
        where.append("datetime(a.created_at) <= datetime(?)")
        params.append(date_to + " 23:59:59")
    if client_q:
        where.append("(LOWER(c.name) LIKE ? OR LOWER(c.telegram_username) LIKE ? OR c.telegram_id LIKE ?)")
        like = f"%{client_q.lower()}%"
        params.extend([like, like, f"%{client_q}%"])
    if media_q:
        where.append("LOWER(COALESCE(a.media, '')) LIKE ?")
        params.append(f"%{media_q.lower()}%")
    if manager_id is not None:
        where.append("a.responsible_manager_id = ?")
        params.append(manager_id)
    if payment_status:
        where.append("a.payment_status = ?")
        params.append(payment_status)
    if archived in ("0", "1"):
        where.append("a.archived = ?")
        params.append(int(archived))
    if q:
        q_like = f"%{q.lower()}%"
        where.append(
            "(" 
            "LOWER(COALESCE(c.name, '')) LIKE ? OR "
            "LOWER(COALESCE(c.telegram_username, '')) LIKE ? OR "
            "CAST(a.external_lead_id AS TEXT) LIKE ? OR "
            "LOWER(COALESCE(c.company, '')) LIKE ? OR "
            "LOWER(COALESCE(a.title, '')) LIKE ?"
            ")"
        )
        params.extend([q_like, q_like, f"%{q}%", q_like, q_like])

    where_sql = " AND ".join(where) if where else "1=1"

    conn = connect()
    try:
        applications = conn.execute(
            f"""
            SELECT
                a.id,
                a.external_lead_id,
                a.created_at,
                a.status,
                a.amount,
                a.payment_status,
                a.deadline_at,
                a.media,
                a.placement_format,
                a.archived,
                c.name AS client_name,
                c.telegram_username,
                c.telegram_id,
                u.full_name AS manager_name,
                COALESCE(files.files_count, 0) AS files_count
            FROM applications a
            JOIN clients c ON c.id = a.client_id
            LEFT JOIN users u ON u.id = a.responsible_manager_id
            LEFT JOIN (
                SELECT application_id, COUNT(*) AS files_count
                FROM attachments
                GROUP BY application_id
            ) files ON files.application_id = a.id
            WHERE {where_sql}
            ORDER BY datetime(a.created_at) DESC
            LIMIT 300
            """,
            params,
        ).fetchall()

        statuses = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM applications GROUP BY status ORDER BY cnt DESC"
        ).fetchall()
        payment_statuses = conn.execute(
            "SELECT payment_status, COUNT(*) AS cnt FROM applications GROUP BY payment_status ORDER BY cnt DESC"
        ).fetchall()
        managers = conn.execute(
            "SELECT id, full_name, username FROM users ORDER BY COALESCE(full_name, username, id)"
        ).fetchall()

        summary = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN archived = 0 THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN archived = 1 THEN 1 ELSE 0 END) AS archived,
                SUM(COALESCE(amount, 0)) AS total_amount
            FROM applications
            """
        ).fetchone()
    finally:
        conn.close()

    return render_template(
        "applications.html",
        applications=applications,
        statuses=statuses,
        payment_statuses=payment_statuses,
        managers=managers,
        summary=summary,
        filters={
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "client": client_q,
            "media": media_q,
            "manager_id": str(manager_id) if manager_id is not None else "",
            "payment_status": payment_status,
            "archived": archived,
            "q": q,
        },
    )


@app.route("/applications/<int:application_id>", methods=["GET"])
def application_detail(application_id: int):
    conn = connect()
    try:
        app_row = conn.execute(
            """
            SELECT
                a.*,
                c.name AS client_name,
                c.telegram_username,
                c.telegram_id,
                c.company,
                c.phone,
                c.email,
                c.client_type,
                u.full_name AS manager_name,
                u.username AS manager_username
            FROM applications a
            JOIN clients c ON c.id = a.client_id
            LEFT JOIN users u ON u.id = a.responsible_manager_id
            WHERE a.id = ?
            """,
            (application_id,),
        ).fetchone()
        if not app_row:
            abort(404)

        status_history = conn.execute(
            """
            SELECT *
            FROM status_history
            WHERE application_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (application_id,),
        ).fetchall()
        comments = conn.execute(
            """
            SELECT *
            FROM comments
            WHERE application_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (application_id,),
        ).fetchall()
        attachments = conn.execute(
            """
            SELECT *
            FROM attachments
            WHERE application_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (application_id,),
        ).fetchall()
        revisions = conn.execute(
            """
            SELECT id, iteration, source_event, changed_by, created_at
            FROM application_revisions
            WHERE application_id = ?
            ORDER BY iteration DESC
            """,
            (application_id,),
        ).fetchall()
        orders = conn.execute(
            """
            SELECT *
            FROM orders
            WHERE application_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (application_id,),
        ).fetchall()
        payments = conn.execute(
            """
            SELECT *
            FROM payments
            WHERE application_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (application_id,),
        ).fetchall()
    finally:
        conn.close()

    return render_template(
        "application_detail.html",
        app_row=app_row,
        status_history=status_history,
        comments=comments,
        attachments=attachments,
        revisions=revisions,
        orders=orders,
        payments=payments,
        all_statuses=ALL_STATUSES,
        msg=(request.args.get("msg") or ""),
    )


@app.route("/applications/<int:application_id>/set-status", methods=["POST"])
def set_status(application_id: int):
    new_status = (request.form.get("status") or "").strip()
    comment = (request.form.get("comment") or "").strip() or None
    notify = request.form.get("notify") == "1"
    notify_text = (request.form.get("notify_text") or "").strip()

    if not new_status or new_status not in STATUS_GROUPS:
        return redirect(url_for("application_detail", application_id=application_id, msg="error"))

    conn = connect()
    try:
        change_status(conn, application_id, new_status, "crm", comment)
        if notify:
            tg_id = get_client_telegram_id(conn, application_id)
            if tg_id:
                text = notify_text or status_change_text(new_status, comment or "")
                send_to_client(tg_id, text)
    except Exception:
        traceback.print_exc()
        return redirect(url_for("application_detail", application_id=application_id, msg="error"))
    finally:
        conn.close()

    return redirect(url_for("application_detail", application_id=application_id, msg="status_updated"))


@app.route("/applications/<int:application_id>/add-comment", methods=["POST"])
def add_comment(application_id: int):
    text = (request.form.get("text") or "").strip()
    is_internal = request.form.get("is_internal") == "1"
    notify = request.form.get("notify") == "1"

    if not text:
        return redirect(url_for("application_detail", application_id=application_id))

    conn = connect()
    try:
        add_crm_comment(conn, application_id, text, "crm", is_internal)
        if notify and not is_internal:
            tg_id = get_client_telegram_id(conn, application_id)
            if tg_id:
                send_to_client(tg_id, text)
    except Exception:
        traceback.print_exc()
        return redirect(url_for("application_detail", application_id=application_id, msg="error"))
    finally:
        conn.close()

    return redirect(url_for("application_detail", application_id=application_id, msg="comment_added"))


@app.route("/applications/<int:application_id>/notify", methods=["POST"])
def notify_client(application_id: int):
    text = (request.form.get("text") or "").strip()

    if not text:
        return redirect(url_for("application_detail", application_id=application_id))

    conn = connect()
    try:
        tg_id = get_client_telegram_id(conn, application_id)
        if tg_id:
            send_to_client(tg_id, text)
    except Exception:
        traceback.print_exc()
        return redirect(url_for("application_detail", application_id=application_id, msg="error"))
    finally:
        conn.close()

    return redirect(url_for("application_detail", application_id=application_id, msg="notified"))


@app.route("/attachments/<int:attachment_id>/download", methods=["GET"])
def download_attachment(attachment_id: int):
    if not BOT_TOKEN:
        abort(503)

    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT source_file_id, filename, mime_type
            FROM attachments
            WHERE id = ?
            """,
            (attachment_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row or not row["source_file_id"]:
        abort(404)

    tg_file_id = str(row["source_file_id"])
    filename = row["filename"] or f"attachment_{attachment_id}"

    try:
        meta_resp = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
            params={"file_id": tg_file_id},
            timeout=10,
        )
        meta = meta_resp.json() if meta_resp.ok else {}
        file_path = ((meta.get("result") or {}).get("file_path") or "").strip()
        if not file_path:
            abort(404)

        file_resp = requests.get(
            f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}",
            timeout=20,
        )
        if not file_resp.ok:
            abort(502)

        content_type = row["mime_type"] or file_resp.headers.get("Content-Type") or "application/octet-stream"
        resp = Response(file_resp.content, mimetype=content_type)
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    except Exception:
        traceback.print_exc()
        abort(502)


@app.route("/api/events", methods=["POST"])
def api_events() -> tuple[dict, int]:
    if CRM_INGEST_API_KEY:
        provided_key = request.headers.get("X-CRM-API-Key", "")
        if provided_key != CRM_INGEST_API_KEY:
            abort(403)

    payload = request.get_json(force=True, silent=True) or {}

    conn = connect()
    try:
        result = ingest_event(conn, payload)
        return result, 200
    except ValueError as exc:
        conn.rollback()
        return {"ok": False, "error": str(exc)}, 400
    except Exception:
        conn.rollback()
        traceback.print_exc()
        return {"ok": False, "error": "internal_error"}, 500
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
