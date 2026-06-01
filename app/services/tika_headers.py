"""
Tika request headers for PDF parsing.

Switch modes via TIKA_PDF_OCR_ENABLED in .env.
"""

from app.config import TIKA_OCR_LANGUAGE, TIKA_OCR_MAX_FILE_SIZE, TIKA_PDF_OCR_ENABLED

# Text-only (no OCR) — use for text-layer PDFs or when Tika has no Tesseract
TIKA_HEADERS_NO_OCR = {
    "X-Tika-PDFOcrStrategy": "no_ocr",
    "X-Tika-PDFextractInlineImages": "false",
    "X-Tika-OCRmaxFileSizeToOcr": "0",
}

# OCR + embedded text (scanned PDFs) — requires Tika full image with Tesseract
TIKA_HEADERS_OCR_BASE = {
    "X-Tika-PDFextractInlineImages": "true",
    "X-Tika-PDFOcrStrategy": "ocr_and_text_extraction",
}


def get_tika_headers() -> dict:
    if TIKA_PDF_OCR_ENABLED:
        return {
            **TIKA_HEADERS_OCR_BASE,
            "X-Tika-OCRmaxFileSizeToOcr": TIKA_OCR_MAX_FILE_SIZE,
            "X-Tika-OCRLanguage": TIKA_OCR_LANGUAGE,
        }
    return TIKA_HEADERS_NO_OCR.copy()
