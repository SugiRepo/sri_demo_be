import os
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

ROOT_DIR = Path(__file__).resolve().parent.parent


def load_environment() -> str:
    """
    Load env files in order (later overrides earlier):
      1. .env
      2. .env.{APP_ENV}  e.g. .env.development, .env.production
    Set APP_ENV before starting to pick the file, e.g. APP_ENV=production
    """
    load_dotenv(ROOT_DIR / ".env")
    app_env = os.getenv("APP_ENV", "development")
    env_specific = ROOT_DIR / f".env.{app_env}"
    if env_specific.is_file():
        load_dotenv(env_specific, override=True)
    return app_env


APP_ENV = load_environment()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/sri_demo",
)

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTICSEARCH_API_KEY = os.getenv("ELASTICSEARCH_API_KEY")
TIKA_ENDPOINT = os.getenv("TIKA_ENDPOINT", "http://localhost:9998/tika")
TIKA_PDF_OCR_ENABLED = os.getenv("TIKA_PDF_OCR_ENABLED", "false").lower() == "true"
TIKA_OCR_LANGUAGE = os.getenv("TIKA_OCR_LANGUAGE", "eng+ind")
TIKA_OCR_MAX_FILE_SIZE = os.getenv("TIKA_OCR_MAX_FILE_SIZE", "52428800")

INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX", "documents")

MIN_PDF_TEXT_CHARS = int(os.getenv("MIN_PDF_TEXT_CHARS", "50"))

API_AUTH_ENABLED = os.getenv("API_AUTH_ENABLED", "true").lower() == "true"


def _parse_api_keys(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(k.strip() for k in raw.split(",") if k.strip())


API_KEYS = _parse_api_keys(os.getenv("API_KEYS"))

_storage_root = Path(
    os.getenv("DOCUMENT_STORAGE_ROOT", "storage/documents")
)
DOCUMENT_STORAGE_ROOT = (
    _storage_root if _storage_root.is_absolute() else ROOT_DIR / _storage_root
)

_es_kwargs: dict = {}
if ELASTICSEARCH_API_KEY:
    _es_kwargs["api_key"] = ELASTICSEARCH_API_KEY

es = Elasticsearch(ELASTICSEARCH_URL, **_es_kwargs)
