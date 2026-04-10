import traceback
import zipfile
from functools import wraps
from io import BytesIO
from typing import Optional

import requests
from flask import Flask, Response, abort, redirect, render_template, request, url_for, make_response

from auth_service import create_auth_code, confirm_auth_code, get_auth_code_status, get_session_user, invalidate_session, validate_and_create_session
from config import ADMIN_IDS, BOT_TOKEN, CRM_INGEST_API_KEY, SESSION_SECRET_KEY
from db import STATUS_GROUPS, connect, run_migrations
from service import add_crm_comment, change_status, get_client_telegram_id, ingest_event
from telegram_notify import send_to_client, status_change_text

ALL_STATUSES = list(STATUS_GROUPS.keys())

app = Flask(__name__)
app.secret_key = SESSION_SECRET_KEY


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


def _get_session_id() -> Optional[str]:
    return request.cookies.get("auth_session")


def _is_authenticated() -> bool:
    session_id = _get_session_id()
    if not session_id:
        return False
    return get_session_user(session_id) is not None


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_session_user():
    session_id = _get_session_id()
    if session_id:
        user = get_session_user(session_id)
        if user:
            return {"session_user": user}
    return {"session_user": None}


@app.route("/health", methods=["GET"])
def health() -> tuple[dict, int]:
    return {"status": "ok"}, 200


@app.route("/login", methods=["GET"])
def login():
    if _is_authenticated():
        return redirect(url_for("applications_list"))

    bot_username = ""
    if BOT_TOKEN:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getMe",
                timeout=5,
            )
            if resp.ok:
                bot_username = resp.json().get("result", {}).get("username", "")
        except Exception:
            pass

    code = request.args.get("code", "").strip() or create_auth_code()
    error = (request.args.get("error") or "").strip() or None
    return render_template(
        "login.html",
        code=code,
        bot_username=bot_username,
        error=error,
    )


@app.route("/request-auth-code", methods=["POST"])
def request_auth_code():
    code = create_auth_code()
    return redirect(url_for("login", code=code))


@app.route("/confirm-auth-code", methods=["POST"])
def confirm_auth_code_route():
    code = (request.form.get("code") or "").strip()
    if not code:
        return redirect(url_for("login", error="Код не указан"))

    session_id = validate_and_create_session(code, ADMIN_IDS)
    if not session_id:
        return redirect(url_for("login", code=code, error="Код не подтвержден ботом или истек. Попробуйте еще раз."))

    resp = make_response(redirect(url_for("applications_list")))
    resp.set_cookie(
        "auth_session",
        session_id,
        max_age=86400,
        secure=True,
        httponly=True,
        samesite="Strict",
    )
    return resp


@app.route("/auth-status", methods=["GET"])
def auth_status() -> tuple[dict, int] | Response:
    if _is_authenticated():
        return {"ok": True, "status": "authenticated", "redirect": url_for("applications_list")}, 200

    code = (request.args.get("code") or "").strip()
    if not code:
        return {"ok": False, "status": "missing_code"}, 400

    status = get_auth_code_status(code)
    if status == "pending":
        return {"ok": True, "status": "pending"}, 200
    if status in ("missing", "expired"):
        return {"ok": False, "status": status}, 404 if status == "missing" else 410

    session_id = validate_and_create_session(code, ADMIN_IDS)
    if not session_id:
        return {"ok": False, "status": "denied"}, 403

    resp = make_response({"ok": True, "status": "authenticated", "redirect": url_for("applications_list")}, 200)
    resp.set_cookie(
        "auth_session",
        session_id,
        max_age=86400,
        secure=True,
        httponly=True,
        samesite="Strict",
    )
    return resp


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session_id = _get_session_id()
    if session_id:
        invalidate_session(session_id)
    resp = make_response(redirect(url_for("login")))
    resp.set_cookie("auth_session", "", max_age=0)
    return resp


@app.route("/", methods=["GET"])
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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


def _tg_file_bytes(tg_file_id: str) -> tuple[bytes, str]:
    meta_resp = requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
        params={"file_id": tg_file_id},
        timeout=10,
    )
    meta = meta_resp.json() if meta_resp.ok else {}
    file_path = ((meta.get("result") or {}).get("file_path") or "").strip()
    if not file_path:
        raise ValueError("telegram_file_path_not_found")

    file_resp = requests.get(
        f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}",
        timeout=20,
    )
    if not file_resp.ok:
        raise ValueError("telegram_file_download_failed")

    return file_resp.content, file_resp.headers.get("Content-Type") or "application/octet-stream"


@app.route("/applications/<int:application_id>/attachments/download-all", methods=["GET"])
@login_required
def download_all_attachments(application_id: int):
    if not BOT_TOKEN:
        abort(503)

    conn = connect()
    try:
        app_row = conn.execute(
            "SELECT external_lead_id FROM applications WHERE id = ?",
            (application_id,),
        ).fetchone()
        if not app_row:
            abort(404)

        rows = conn.execute(
            """
            SELECT id, source_file_id, filename
            FROM attachments
            WHERE application_id = ?
            ORDER BY id
            """,
            (application_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        abort(404)

    zip_buf = BytesIO()
    added = 0
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, row in enumerate(rows, start=1):
            tg_file_id = str(row["source_file_id"] or "")
            if not tg_file_id:
                continue
            try:
                file_bytes, _ = _tg_file_bytes(tg_file_id)
            except Exception:
                traceback.print_exc()
                continue

            name = (row["filename"] or "").strip() or f"file_{idx}"
            if "." not in name:
                name = f"{name}.bin"
            zf.writestr(name, file_bytes)
            added += 1

    if added == 0:
        abort(502)

    zip_buf.seek(0)
    lead_no = app_row["external_lead_id"]
    resp = Response(zip_buf.getvalue(), mimetype="application/zip")
    resp.headers["Content-Disposition"] = f'attachment; filename="lead_{lead_no}_files.zip"'
    return resp


@app.route("/attachments/<int:attachment_id>/download", methods=["GET"])
@login_required
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
        file_bytes, detected_type = _tg_file_bytes(tg_file_id)
        content_type = row["mime_type"] or detected_type
        resp = Response(file_bytes, mimetype=content_type)
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    except Exception:
        traceback.print_exc()
        abort(502)


@app.route("/api/auth/confirm-code", methods=["POST"])
def api_confirm_auth_code() -> tuple[dict, int]:
    payload = request.get_json(force=True, silent=True) or {}
    provided_token = (payload.get("bot_token") or "").strip()
    code = (payload.get("code") or "").strip()
    telegram_id_raw = payload.get("telegram_id")

    if not BOT_TOKEN or provided_token != BOT_TOKEN:
        return {"ok": False, "error": "unauthorized"}, 403
    if not code or telegram_id_raw is None:
        return {"ok": False, "error": "missing_fields"}, 400

    try:
        telegram_id = int(telegram_id_raw)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid_telegram_id"}, 400

    if confirm_auth_code(code, telegram_id):
        return {"ok": True}, 200
    return {"ok": False, "error": "invalid_or_expired_code"}, 400


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
