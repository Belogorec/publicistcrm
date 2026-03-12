import os

from dotenv import load_dotenv

load_dotenv()

CRM_INGEST_API_KEY = os.getenv("CRM_INGEST_API_KEY", "").strip()
CRM_DB_PATH = os.getenv(
    "CRM_DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "projectpress_crm.db"),
).strip()
CRM_DEFAULT_MANAGER = os.getenv("CRM_DEFAULT_MANAGER", "").strip() or None
