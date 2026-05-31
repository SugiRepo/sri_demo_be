"""
Router-level utilities Public API v1:
- /api/v1/info       — informasi versi API & build (untuk monitoring eksternal)
- /api/v1/errors     — daftar kode error standar (kontrak ke konsumen)
- /api/v1/audit-log  — entri audit terbaru (KAK §1.5.3.b jejak aktivitas)
"""

from __future__ import annotations

import platform
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.api_v1.envelope import API_VERSION, SuccessResponse, make_meta
from app.api_v1.errors import DEFAULT_HTTP_STATUS, ErrorCode
from app.services import audit_log

router = APIRouter(tags=["Sistem"])


class ApiInfo(BaseModel):
    api_version: str = API_VERSION
    server_time: str
    python_version: str
    platform: str
    docs_url: str = Field(default="/docs", description="Swagger UI interaktif.")
    openapi_url: str = Field(default="/openapi.json", description="Spesifikasi OpenAPI mentah.")


class ErrorCodeEntry(BaseModel):
    code: str
    http_status: int
    description: str


# Penjelasan ringkas tiap kode (untuk dokumentasi konsumen).
ERROR_DESCRIPTIONS: dict[ErrorCode, str] = {
    ErrorCode.BAD_REQUEST: "Permintaan tidak valid.",
    ErrorCode.VALIDATION_ERROR: "Validasi schema/body gagal.",
    ErrorCode.UNAUTHORIZED: "Kredensial tidak ada / tidak valid.",
    ErrorCode.FORBIDDEN: "Tidak punya hak akses untuk operasi ini.",
    ErrorCode.ARSIP_NOT_FOUND: "Arsip tidak ditemukan di sistem.",
    ErrorCode.DOCUMENT_NOT_INDEXED: "Arsip ada tetapi belum ter-index.",
    ErrorCode.UNSUPPORTED_FILE: "Format file tidak didukung (hanya PDF).",
    ErrorCode.PDF_TOO_SHORT: "Konten PDF terlalu pendek untuk di-indeks.",
    ErrorCode.PDF_NOT_READABLE: "PDF tidak dapat dibaca / scanned image tanpa OCR.",
    ErrorCode.RATE_LIMITED: "Terlalu banyak request — coba lagi nanti.",
    ErrorCode.INTERNAL_ERROR: "Kesalahan internal pada server.",
    ErrorCode.SEARCH_ENGINE_UNAVAILABLE: "Mesin pencari tidak tersedia.",
    ErrorCode.SEARCH_ENGINE_ERROR: "Mesin pencari menolak/gagal request.",
    ErrorCode.EXTRACTION_ERROR: "Ekstraksi metadata gagal.",
    ErrorCode.DEPENDENCY_TIMEOUT: "Layanan dependency timeout.",
}


class ErrorCatalog(BaseModel):
    total: int
    items: list[ErrorCodeEntry]


class AuditEntry(BaseModel):
    ts: str
    request_id: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    query: Optional[str] = None
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None


class AuditLogPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AuditEntry]


@router.get(
    "/info",
    response_model=SuccessResponse[ApiInfo],
    summary="Informasi versi API",
)
def api_info(request: Request) -> SuccessResponse[ApiInfo]:
    info = ApiInfo(
        server_time=datetime.now(timezone.utc).isoformat(),
        python_version=platform.python_version(),
        platform=f"{platform.system()} {platform.release()}",
    )
    return SuccessResponse[ApiInfo](
        data=info,
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )


@router.get(
    "/errors",
    response_model=SuccessResponse[ErrorCatalog],
    summary="Katalog kode error standar",
    description=(
        "Daftar lengkap kode error yang bisa muncul di response v1. "
        "Konsumen eksternal dapat melakukan logic switch berdasar `code`."
    ),
)
def error_catalog(request: Request) -> SuccessResponse[ErrorCatalog]:
    items = [
        ErrorCodeEntry(
            code=code.value,
            http_status=DEFAULT_HTTP_STATUS[code],
            description=ERROR_DESCRIPTIONS.get(code, ""),
        )
        for code in ErrorCode
    ]
    return SuccessResponse[ErrorCatalog](
        data=ErrorCatalog(total=len(items), items=items),
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )


@router.get(
    "/audit-log",
    response_model=SuccessResponse[AuditLogPage],
    summary="Jejak aktivitas API (audit log)",
    description=(
        "Mengembalikan entri audit log terbaru. Dipakai untuk traceability "
        "antar sistem (KAK §1.5.3.b). Untuk produksi, audit log sebaiknya "
        "dipindah ke datastore terindeks (Elasticsearch / Postgres)."
    ),
)
def audit_log_view(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> SuccessResponse[AuditLogPage]:
    entries_raw = audit_log.read_recent(limit=limit, offset=offset)
    entries = [AuditEntry(**e) for e in entries_raw]
    page = AuditLogPage(
        total=audit_log.total_count(),
        limit=limit,
        offset=offset,
        items=entries,
    )
    return SuccessResponse[AuditLogPage](
        data=page,
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )
