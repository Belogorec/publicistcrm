import secrets
from datetime import datetime, timedelta
from typing import Optional

from config import AUTH_SESSION_LIFETIME, CRM_LOGIN, CRM_PASSWORD
from db import connect


def _generate_session_id() -> str:
    return secrets.token_urlsafe(32)


def create_session(login: str, password: str) -> Optional[str]:
    if login != CRM_LOGIN or password != CRM_PASSWORD:
        return None

    session_id = _generate_session_id()
    expires_at = (datetime.utcnow() + timedelta(seconds=AUTH_SESSION_LIFETIME)).isoformat()

    conn = connect()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (datetime.utcnow().isoformat(),))
        conn.execute(
            """
            INSERT INTO auth_sessions (session_id, telegram_id, username, full_name, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, login, login, "Administrator", expires_at),
        )
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
