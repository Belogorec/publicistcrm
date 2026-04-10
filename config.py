import os

from dotenv import load_dotenv

load_dotenv()

CRM_INGEST_API_KEY = os.getenv("CRM_INGEST_API_KEY", "").strip()
CRM_DB_PATH = os.getenv(
    "CRM_DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "projectpress_crm.db"),
).strip()
CRM_DEFAULT_MANAGER = os.getenv("CRM_DEFAULT_MANAGER", "").strip() or None
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
_admin_raw = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = [int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()]
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "change-me-in-production").strip()
AUTH_TOKEN_LIFETIME = int(os.getenv("AUTH_TOKEN_LIFETIME", "86400").strip() or "86400")
