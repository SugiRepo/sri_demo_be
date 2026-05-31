"""
Endpoint domain Arsip — Public API v1.

Semua endpoint mengembalikan `SuccessResponse[T]` envelope.
Error dilempar via `ApiError` dengan kode standar di `errors.py`.

Endpoint:
    GET    /api/v1/arsip                — list & search arsip (pagination)
    GET    /api/v1/arsip/{document_id}  — detail arsip + status indeks
    POST   /api/v1/arsip                — upload PDF baru
    GET    /api/v1/arsip/{id}/metadata  — ekstraksi metadata Layer 1
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api_v1.envelope import SuccessResponse, make_meta
from app.api_v1.errors import ApiError, ErrorCode
from app.config import MIN_PDF_TEXT_CHARS
from app.database import get_session
from app.services.document_db import (
    create_document,
    get_document_by_document_id,
)
from app.services.document_search import (
    ElasticsearchConnectionError,
    ElasticsearchSearchError,
    search_documents,
)
from app.services.metadata_extraction import ExtractionResult, extract_metadata
from app.services.pdf_ingest import process_and_index_pdf
from app.services.pdf_validation import (
    PdfValidationError,
    is_pdf_file,
    validate_pdf_for_upload,
)
from app.config import INDEX_NAME, es

from fastapi import Depends

logger = logging.getLogger("app.api_v1.arsip")

router = APIRouter(prefix="/arsip", tags=["Arsip (Naskah Dinas)"])


# ---------------------------------------------------------------------------
# Domain models exposed di OpenAPI (kontrak untuk konsumen eksternal)
# ---------------------------------------------------------------------------


class ArsipDetail(BaseModel):
    """Representasi 1 arsip + status indeksnya."""

    document_id: str = Field(..., description="UUID arsip, stabil sepanjang siklus hidup.")
    filename: str = Field(..., description="Nama file asli saat diunggah.")
    status: str = Field(
        ...,
        description="Status indeks: 'processing', 'indexed', atau 'failed'.",
    )
    page_count: Optional[int] = Field(
        default=None, description="Jumlah halaman yang sukses ter-index."
    )
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class ArsipUploadAccepted(BaseModel):
    """Response setelah upload diterima (proses indeks berjalan async)."""

    document_id: str
    filename: str
    status: str = Field(default="processing")
    message: str = Field(
        default="File diterima. Proses ekstraksi & indeks berjalan di background."
    )


class ArsipSearchHit(BaseModel):
    """Satu baris hasil pencarian (collapsed per dokumen)."""

    document_id: str
    filename: Optional[str]
    publish_date: Optional[str]
    page_number: Optional[int]
    score: Optional[float]
    content_snippet: str = Field(
        ...,
        description="Cuplikan isi dengan highlight Elasticsearch <em>...</em>.",
    )


class ArsipSearchResult(BaseModel):
    query: str
    search_mode: str = Field(..., description="'phrase' jika kueri di-quote, 'flexible' jika tidak.")
    total_pages_matched: int
    total_documents: int
    documents: list[ArsipSearchHit]


class MetadataExtractionData(BaseModel):
    document_id: str
    filename: Optional[str]
    page_used: int
    extraction: ExtractionResult


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{document_id}",
    response_model=SuccessResponse[ArsipDetail],
    summary="Detail arsip",
    description=(
        "Mengambil status & metadata dasar 1 arsip berdasarkan `document_id`. "
        "Untuk metadata terstruktur (nomor surat, perihal, dst.), gunakan "
        "endpoint `GET /api/v1/arsip/{id}/metadata`."
    ),
)
def get_arsip(
    document_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> SuccessResponse[ArsipDetail]:
    doc = get_document_by_document_id(session, document_id)
    if doc is None:
        raise ApiError(
            ErrorCode.ARSIP_NOT_FOUND,
            f"Arsip dengan document_id '{document_id}' tidak ditemukan.",
            details={"document_id": document_id},
        )

    detail = ArsipDetail(
        document_id=doc.document_id,
        filename=doc.filename,
        status=doc.status,
        page_count=doc.page_count,
        error_message=doc.error_message,
        created_at=doc.created_at.isoformat(),
        updated_at=doc.updated_at.isoformat(),
    )
    return SuccessResponse[ArsipDetail](
        data=detail,
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )


@router.get(
    "",
    response_model=SuccessResponse[ArsipSearchResult],
    summary="Cari arsip (full-text)",
    description=(
        "Pencarian full-text pada konten arsip yang sudah ter-indeks di "
        "Elasticsearch. Hasil di-collapse 1 baris per dokumen, halaman dengan "
        "skor tertinggi yang ditampilkan. Gunakan tanda kutip `\"...\"` untuk "
        "frasa eksak."
    ),
)
def list_arsip(
    request: Request,
    q: str = Query(..., min_length=1, description="Kata kunci pencarian."),
    size: int = Query(20, ge=1, le=100, description="Jumlah hasil maksimum."),
    from_: int = Query(0, ge=0, alias="from", description="Offset pagination."),
) -> SuccessResponse[ArsipSearchResult]:
    try:
        raw = search_documents(q, size=size, from_=from_)
    except ValueError as exc:
        raise ApiError(ErrorCode.BAD_REQUEST, str(exc)) from exc
    except ElasticsearchConnectionError as exc:
        raise ApiError(
            ErrorCode.SEARCH_ENGINE_UNAVAILABLE,
            exc.message,
        ) from exc
    except ElasticsearchSearchError as exc:
        raise ApiError(
            ErrorCode.SEARCH_ENGINE_ERROR,
            exc.message,
        ) from exc

    result = ArsipSearchResult(**raw)
    return SuccessResponse[ArsipSearchResult](
        data=result,
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )


@router.post(
    "",
    response_model=SuccessResponse[ArsipUploadAccepted],
    status_code=202,
    summary="Unggah arsip baru (async indexing)",
    description=(
        "Mengunggah file PDF naskah dinas. Server segera membalas 202 Accepted "
        "dengan `document_id`; ekstraksi (Tika) dan indexing (Elasticsearch) "
        "berjalan di background. Status indeks dapat dipantau via "
        "`GET /api/v1/arsip/{document_id}`."
    ),
)
async def upload_arsip(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="File PDF naskah dinas."),
    session: Session = Depends(get_session),
) -> SuccessResponse[ArsipUploadAccepted]:
    document_id = str(uuid.uuid4())
    temp_file_path = f"temp_{document_id}_{file.filename}"

    with open(temp_file_path, "wb") as buffer:
        buffer.write(await file.read())

    if is_pdf_file(temp_file_path, file.filename):
        try:
            validate_pdf_for_upload(temp_file_path, MIN_PDF_TEXT_CHARS)
        except PdfValidationError as exc:
            os.remove(temp_file_path)
            raise ApiError(
                ErrorCode.PDF_NOT_READABLE,
                exc.message,
                details={"validation_code": exc.code, "filename": file.filename},
            ) from exc
    else:
        os.remove(temp_file_path)
        raise ApiError(
            ErrorCode.UNSUPPORTED_FILE,
            "Format file tidak didukung. Hanya PDF yang diterima.",
            details={"filename": file.filename, "content_type": file.content_type},
        )

    create_document(session, document_id=document_id, filename=file.filename or "")
    background_tasks.add_task(
        process_and_index_pdf,
        file_path=temp_file_path,
        document_id=document_id,
        original_filename=file.filename,
    )

    accepted = ArsipUploadAccepted(
        document_id=document_id,
        filename=file.filename or "",
    )
    return SuccessResponse[ArsipUploadAccepted](
        data=accepted,
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )


@router.get(
    "/{document_id}/metadata",
    response_model=SuccessResponse[MetadataExtractionData],
    summary="Ekstraksi metadata Layer 1 (regex)",
    description=(
        "Menjalankan ekstraksi metadata terstruktur (nomor surat, sifat, "
        "lampiran, perihal, tanggal, klasifikasi, NIP, penerima) pada teks "
        "halaman pertama dokumen. Layer 1 = rule-based regex, latency "
        "&lt; 50 ms. Layer 2 (NER IndoBERT) akan dipanggil otomatis untuk "
        "field free-form bila tersedia."
    ),
)
def get_arsip_metadata(
    document_id: str,
    request: Request,
) -> SuccessResponse[MetadataExtractionData]:
    try:
        response = es.search(
            index=INDEX_NAME,
            query={"term": {"document_id": document_id}},
            sort=[{"page_number": "asc"}],
            size=1,
            _source=["filename", "content", "page_number"],
        )
    except Exception as exc:
        raise ApiError(
            ErrorCode.SEARCH_ENGINE_UNAVAILABLE,
            f"Tidak bisa mengambil dokumen dari index: {exc}",
        ) from exc

    hits = response.get("hits", {}).get("hits", [])
    if not hits:
        raise ApiError(
            ErrorCode.ARSIP_NOT_FOUND,
            f"Arsip '{document_id}' belum ter-index atau tidak ditemukan.",
            details={"document_id": document_id},
        )

    source = hits[0].get("_source", {})
    content = source.get("content") or ""
    if not content.strip():
        raise ApiError(
            ErrorCode.DOCUMENT_NOT_INDEXED,
            "Halaman pertama tidak punya teks untuk diekstrak.",
        )

    try:
        extraction = extract_metadata(content)
    except Exception as exc:
        raise ApiError(
            ErrorCode.EXTRACTION_ERROR,
            f"Ekstraksi metadata gagal: {exc}",
        ) from exc

    payload = MetadataExtractionData(
        document_id=document_id,
        filename=source.get("filename"),
        page_used=int(source.get("page_number") or 1),
        extraction=extraction,
    )
    return SuccessResponse[MetadataExtractionData](
        data=payload,
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )
