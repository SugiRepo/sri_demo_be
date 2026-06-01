import logging
import os
from io import BytesIO

from pypdf import PdfReader

from app.services.pdf_watermark import apply_watermark_to_pdf
from app.services.watermark_db import update_watermark_in_background
from app.services.watermark_storage import save_watermarked_pdf

logger = logging.getLogger("app.services.watermark_process")


def process_watermark_pdf(
    temp_file_path: str,
    watermark_id: str,
    watermark_wording: str,
    document_path: str,
    file_name_output: str,
    *,
    opacity: float = 0.25,
    angle: float = 45,
) -> None:
    try:
        logger.info(
            "[1/3] Watermark task started watermark_id=%s file=%s",
            watermark_id,
            temp_file_path,
        )
        with open(temp_file_path, "rb") as f:
            pdf_bytes = f.read()

        result = apply_watermark_to_pdf(
            pdf_bytes,
            watermark_wording,
            opacity=opacity,
            angle=angle,
        )
        page_count = len(PdfReader(BytesIO(result)).pages)

        logger.info(
            "[2/3] Saving watermarked PDF watermark_id=%s pages=%s",
            watermark_id,
            page_count,
        )
        save_watermarked_pdf(result, document_path, file_name_output)

        update_watermark_in_background(
            watermark_id,
            "success",
            number_of_page=page_count,
            change_by="system",
        )
        logger.info("[3/3] Watermark complete watermark_id=%s", watermark_id)
    except Exception:
        logger.exception("[STOP] Watermark failed watermark_id=%s", watermark_id)
        update_watermark_in_background(watermark_id, "failed", change_by="system")
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.info("Temp file removed: %s", temp_file_path)
