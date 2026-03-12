import html
import logging

import requests

from config import BOT_TOKEN

_TG_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_to_client(telegram_id: str, text: str) -> bool:
    """Send a plain-text message directly to a Telegram user via Bot API."""
    if not BOT_TOKEN or not telegram_id or not text:
        return False
    try:
        resp = requests.post(
            _TG_API.format(token=BOT_TOKEN),
            json={"chat_id": telegram_id, "text": text},
            timeout=8,
        )
        if not resp.ok:
            logging.warning("telegram_notify: %s %s", resp.status_code, resp.text[:200])
        return resp.ok
    except Exception as exc:
        logging.warning("telegram_notify error: %s", exc)
        return False


def status_change_text(new_status: str, comment: str = "") -> str:
    """Build a default notification message for a status change."""
    msg = f"Статус вашей заявки изменён: <b>{html.escape(new_status)}</b>"
    if comment:
        msg += f"\n\n{html.escape(comment)}"
    return msg
