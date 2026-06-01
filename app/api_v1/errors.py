"""
Kode error standar untuk Public API v1.

Setiap kode bersifat stabil — konsumen eksternal aman membuat logic switch
berdasarkan kode ini. Bila pesan diterjemahkan/diubah, kode tetap sama.
"""

from enum import Enum

from fastapi import HTTPException


class ErrorCode(str, Enum):
    # 4xx — kesalahan dari sisi konsumen
    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    ARSIP_NOT_FOUND = "ARSIP_NOT_FOUND"
    WATERMARK_NOT_FOUND = "WATERMARK_NOT_FOUND"
    WATERMARK_NOT_READY = "WATERMARK_NOT_READY"
    WATERMARK_FILE_MISSING = "WATERMARK_FILE_MISSING"
    DOCUMENT_NOT_INDEXED = "DOCUMENT_NOT_INDEXED"
    DOCUMENT_FILE_MISSING = "DOCUMENT_FILE_MISSING"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    PDF_TOO_SHORT = "PDF_TOO_SHORT"
    PDF_NOT_READABLE = "PDF_NOT_READABLE"
    PDF_GENERATE_FAILED = "PDF_GENERATE_FAILED"
    RATE_LIMITED = "RATE_LIMITED"

    # 5xx — kegagalan dari sisi server / dependency
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SEARCH_ENGINE_UNAVAILABLE = "SEARCH_ENGINE_UNAVAILABLE"
    SEARCH_ENGINE_ERROR = "SEARCH_ENGINE_ERROR"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"
    DEPENDENCY_TIMEOUT = "DEPENDENCY_TIMEOUT"


# Mapping default kode → HTTP status. Endpoint bisa override bila perlu.
DEFAULT_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.ARSIP_NOT_FOUND: 404,
    ErrorCode.WATERMARK_NOT_FOUND: 404,
    ErrorCode.WATERMARK_NOT_READY: 409,
    ErrorCode.WATERMARK_FILE_MISSING: 404,
    ErrorCode.DOCUMENT_NOT_INDEXED: 409,
    ErrorCode.DOCUMENT_FILE_MISSING: 404,
    ErrorCode.UNSUPPORTED_FILE: 415,
    ErrorCode.PDF_TOO_SHORT: 400,
    ErrorCode.PDF_NOT_READABLE: 400,
    ErrorCode.PDF_GENERATE_FAILED: 500,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.SEARCH_ENGINE_UNAVAILABLE: 503,
    ErrorCode.SEARCH_ENGINE_ERROR: 502,
    ErrorCode.EXTRACTION_ERROR: 500,
    ErrorCode.DEPENDENCY_TIMEOUT: 504,
}


class ApiError(HTTPException):
    """
    Exception kustom yang membawa kode error stabil + detail terstruktur.

    Akan ditangkap oleh `api_error_handler` di middleware.py dan
    diserialisasi sebagai ErrorResponse envelope.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int | None = None,
        details: dict | None = None,
    ):
        self.code = code
        self.error_message = message
        self.error_details = details
        super().__init__(
            status_code=status_code or DEFAULT_HTTP_STATUS[code],
            detail=message,
        )
