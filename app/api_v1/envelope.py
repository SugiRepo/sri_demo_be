"""
Standar response envelope untuk Public API v1.

Semua endpoint v1 harus mengembalikan salah satu dari dua bentuk:
- Sukses: { "status": "success", "data": <T>, "meta": {...} }
- Gagal:  { "status": "error",   "error": {...},  "meta": {...} }

Konvensi ini selaras dengan praktik umum SPBE / Open API design,
memudahkan konsumen eksternal melakukan parsing yang konsisten.
"""

from datetime import datetime, timezone
from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

API_VERSION = "1.0.0"


class ResponseMeta(BaseModel):
    """Metadata yang menyertai setiap response (sukses maupun gagal)."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "request_id": "8c1f6a9c-7b8e-4cb5-bf1a-3a4e57c3a801",
            "timestamp": "2026-05-31T13:00:00.000+00:00",
            "api_version": "1.0.0",
            "execution_time_ms": 12.34,
        }
    })

    request_id: str = Field(
        ...,
        description="UUID unik tiap request, dipakai untuk korelasi log antar sistem.",
    )
    timestamp: str = Field(
        ...,
        description="Waktu server saat response dibentuk, dalam ISO-8601.",
    )
    api_version: str = Field(default=API_VERSION)
    execution_time_ms: Optional[float] = Field(
        default=None,
        description="Latensi eksekusi server dalam milidetik (tanpa network).",
    )


class ErrorDetail(BaseModel):
    """Format error standar yang konsisten antar endpoint."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "code": "ARSIP_NOT_FOUND",
            "message": "Arsip dengan id 'abc-123' tidak ditemukan.",
            "details": {"document_id": "abc-123"},
        }
    })

    code: str = Field(
        ...,
        description="Kode error stabil (machine-readable). Lihat /api/v1/errors.",
    )
    message: str = Field(..., description="Pesan dapat dibaca manusia.")
    details: Optional[dict[str, Any]] = Field(
        default=None,
        description="Konteks tambahan: field yang tidak valid, dst.",
    )


class SuccessResponse(BaseModel, Generic[T]):
    """Response sukses generik dengan payload `data` bertipe T."""

    status: Literal["success"] = "success"
    data: T
    meta: ResponseMeta


class ErrorResponse(BaseModel):
    """Response gagal dengan detail error terstruktur."""

    status: Literal["error"] = "error"
    error: ErrorDetail
    meta: ResponseMeta


def make_meta(
    request_id: str,
    execution_time_ms: Optional[float] = None,
) -> ResponseMeta:
    return ResponseMeta(
        request_id=request_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        execution_time_ms=execution_time_ms,
    )
