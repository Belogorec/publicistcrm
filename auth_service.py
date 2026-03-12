import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from config import AUTH_TOKEN_LIFETIME
from db import connect


def _generate_session_id() -> str:
    return secrets.token_urlsafe(32)


def create_auth_code() -> str:
    conn = connect()
    try:
        raw_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        code = f"AUTH-{raw_code}"
        expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        conn.execute(
            "INSERT INTO auth_codes (code, confirmed, expires_at) VALUES (?, 0, ?)",
            (code, expires_at),
        )
        conn.commit()
        return code
    finally:
        conn.close()


def get_auth_code_status(code: str) -> str:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT confirmed, expires_at FROM auth_codes WHERE code = ?",
            (code,),
        ).fetchone()
        if not row:
            return "missing"
        if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            return "expired"
        if row["confirmed"]:
            return "confirmed"
        return "pending"
    finally:
        conn.close()


def confirm_auth_code(code: str, telegram_id: int) -> bool:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, expires_at FROM auth_codes WHERE code = ? AND confirmed = 0",
            (code,),
        ).fetchone()
        if not row:
            return False
        if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            return False
        conn.execute(
            "UPDATE auth_codes SET telegram_id = ?, confirmed = 1 WHERE id = ?",
            (str(telegram_id), row["id"]),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def validate_and_create_session(code: str, admin_ids) -> Optional[str]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, telegram_id, expires_at FROM auth_codes WHERE code = ? AND confirmed = 1",
            (code,),
        ).fetchone()
        if not row:
            return None
        if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            return None
        telegram_id = int(row["telegram_id"])
        if telegram_id not in admin_ids:
            return None

        user_row = conn.execute(
            "SELECT username, full_name FROM users WHERE telegram_id = ?",
            (str(telegram_id),),
        ).fetchone()
        username = (user_row["username"] or "") if user_row else str(telegram_id)
        full_name = (user_row["full_name"] or "") if user_row else ""
        session_id = _generate_session_id()
        expires_at = (datetime.utcnow() + timedelta(seconds=AUTH_TOKEN_LIFETIME)).isoformat()
        conn.execute(
            """
            INSERT INTO auth_sessions (session_id, telegram_id, username, full_name, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, str(telegram_id), username, full_name, expires_at),
        )
        conn.execute("DELETE FROM auth_codes WHERE id = ?", (row["id"],))
        conn.commit()
        return session_id
    finally:
        conn.close()


def get_session_user(session_id: str) -> Optional[dict]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT telegram_id, username, full_name, expires_at FROM auth_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return None
        return {
            "telegram_id": row["telegram_id"],
            "username": row["username"],
            "full_name": row["full_name"],
        }
    finally:
        conn.close()


def invalidate_session(session_id: str) -> None:
    conn = connect()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()