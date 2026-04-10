from flask import Response, make_response, redirect, render_template, request, url_for

import requests

from auth_service import create_auth_code, confirm_auth_code, get_auth_code_status, validate_and_create_session
from config import ADMIN_IDS, BOT_TOKEN


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
