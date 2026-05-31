"""
Middleware untuk Public API v1:
- Generate `request_id` per request, ekspos lewat header `X-Request-ID`.
- Catat audit trail tiap call (method, path, status, latency, IP, UA).
- Convert ApiError + HTTPException + Exception ke ErrorResponse envelope.

Mengikuti standar SPBE / OWASP — request id wajib agar tracing antar service mudah.
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.api_v1.envelope import ErrorResponse, ErrorDetail, make_meta
from app.api_v1.errors import ApiError, ErrorCode
from app.services import audit_log

logger = logging.getLogger("app.api_v1.middleware")

V1_PREFIX = "/api/v1"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Pasang `request.state.request_id` dan `request.state.start_time`
    di setiap request — diakses oleh exception handler & endpoint.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.start_time = time.perf_counter()

        response = await call_next(request)

        execution_ms = (time.perf_counter() - request.state.start_time) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{execution_ms:.2f}"
        return response


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Catat seluruh request ke /api/v1/* sebagai 1 baris audit log.
    Endpoint internal (mis. /docs, /openapi.json, /health legacy)
    tidak ikut dicatat agar log tidak ramai.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        track = path.startswith(V1_PREFIX)

        response = await call_next(request)

        if track:
            execution_ms = (
                (time.perf_counter() - request.state.start_time) * 1000
                if hasattr(request.state, "start_time")
                else None
            )
            try:
                audit_log.write_entry(
                    {
                        "request_id": getattr(request.state, "request_id", None),
                        "method": request.method,
                        "path": path,
                        "query": str(request.url.query) or None,
                        "status_code": response.status_code,
                        "latency_ms": (
                            round(execution_ms, 2) if execution_ms is not None else None
                        ),
                        "client_ip": request.client.host if request.client else None,
                        "user_agent": request.headers.get("user-agent"),
                    }
                )
            except Exception:
                logger.exception("Audit middleware gagal mencatat entri")

        return response


def _envelope_error_response(
    request: Request,
    *,
    status_code: int,
    code: ErrorCode | str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    start = getattr(request.state, "start_time", None)
    execution_ms = (time.perf_counter() - start) * 1000 if start else None

    payload = ErrorResponse(
        error=ErrorDetail(
            code=code.value if isinstance(code, ErrorCode) else str(code),
            message=message,
            details=details,
        ),
        meta=make_meta(request_id=request_id, execution_time_ms=execution_ms),
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return _envelope_error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.error_message,
        details=exc.error_details,
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Ambil hanya field path & pesan untuk klien — jangan bocorkan internal repr.
    details = {
        "fields": [
            {"loc": list(err.get("loc", [])), "msg": err.get("msg")}
            for err in exc.errors()
        ]
    }
    return _envelope_error_response(
        request,
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message="Validasi input gagal.",
        details=details,
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.error(
        "Unhandled exception path=%s: %s\n%s",
        request.url.path,
        exc,
        traceback.format_exc(),
    )
    return _envelope_error_response(
        request,
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message="Terjadi kesalahan internal pada server.",
    )


def install_v1_middleware(app: FastAPI) -> None:
    """Pasang middleware & exception handler v1 ke aplikasi."""
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
