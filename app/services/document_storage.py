import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.config import DOCUMENT_STORAGE_ROOT

logger = logging.getLogger("app.services.document_storage")


def build_storage_path(
    document_id: str,
    original_filename: str,
    *,
    when: datetime | None = None,
) -> Path:
    """
    {DOCUMENT_STORAGE_ROOT}/{year}/{YYYYMMDD}/{document_id}_{filename}
    """
    when = when or datetime.now(timezone.utc)
    year = when.strftime("%Y")
    monthdate = when.strftime("%Y%m%d")
    safe_name = Path(original_filename or "document").name
    dest_name = f"{document_id}_{safe_name}"
    return DOCUMENT_STORAGE_ROOT / year / monthdate / dest_name


def save_document_to_storage(
    source_path: str,
    document_id: str,
    original_filename: str,
) -> str:
    """Copy uploaded file into dated storage. Returns absolute path as string."""
    dest_path = build_storage_path(document_id, original_filename)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, dest_path)
    logger.info(
        "Document archived document_id=%s path=%s",
        document_id,
        dest_path,
    )
    return str(dest_path.resolve())
