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
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "change-me-in-production").strip()
CRM_LOGIN = os.getenv("CRM_LOGIN", "admin").strip() or "admin"
CRM_PASSWORD = os.getenv("CRM_PASSWORD", "74952870022").strip() or "74952870022"
AUTH_SESSION_LIFETIME = int(
    os.getenv("AUTH_SESSION_LIFETIME", os.getenv("AUTH_TOKEN_LIFETIME", "86400")).strip() or "86400"
)
