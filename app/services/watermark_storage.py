import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import DOCUMENT_STORAGE_ROOT

logger = logging.getLogger("app.services.watermark_storage")


def build_document_path(when: datetime | None = None) -> str:
    """Relative directory: watermarks/{YYYY}/{YYYYMMDD}."""
    when = when or datetime.now(timezone.utc)
    year = when.strftime("%Y")
    monthdate = when.strftime("%Y%m%d")
    return f"watermarks/{year}/{monthdate}"


def build_output_filename(watermark_id: str, original_filename: str) -> str:
    safe_name = Path(original_filename or "document.pdf").name
    if safe_name.lower().endswith(".pdf"):
        stem = safe_name[:-4]
    else:
        stem = safe_name
    return f"{watermark_id}_{stem}-watermarked.pdf"


def resolve_output_file(document_path: str, file_name_output: str) -> Path:
    return DOCUMENT_STORAGE_ROOT / document_path / file_name_output


def save_watermarked_pdf(
    pdf_bytes: bytes,
    document_path: str,
    file_name_output: str,
) -> str:
    dest_path = resolve_output_file(document_path, file_name_output)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(pdf_bytes)
    logger.info("Watermarked PDF saved path=%s", dest_path)
    return str(dest_path.resolve())
