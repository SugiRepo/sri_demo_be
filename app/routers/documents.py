import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api_v1.envelope import ResponseMeta, SuccessResponse, make_meta
from app.api_v1.errors import ApiError, ErrorCode
from app.config import MIN_PDF_TEXT_CHARS, TIKA_PDF_OCR_ENABLED
from app.database import get_session
from app.models.document import Document
from app.services.document_db import create_document, get_document_by_document_id
from app.services.document_search import (
    ElasticsearchConnectionError,
    ElasticsearchSearchError,
    search_documents,
)
from app.services.document_storage import resolve_document_file
from app.services.pdf_ingest import process_and_index_pdf
from app.services.pdf_validation import (
    PdfValidationError,
    is_pdf_file,
    validate_pdf_for_upload,
)

router = APIRouter(tags=["Documents"])
logger = logging.getLogger("app.routers.documents")

DOCUMENT_STATUS_INDEXED = "indexed"

_PDF_VALIDATION_TO_ERROR: dict[str, ErrorCode] = {
    "invalid_pdf": ErrorCode.UNSUPPORTED_FILE,
    "empty_pdf": ErrorCode.PDF_NOT_READABLE,
    "pdf_read_error": ErrorCode.PDF_NOT_READABLE,
    "no_extractable_text": ErrorCode.PDF_TOO_SHORT,
}


class DocumentUploadAccepted(BaseModel):
    message: str
    document_id: str
    filename: Optional[str]
    status: str = Field(default="processing")


class DocumentSearchHit(BaseModel):
    document_id: Optional[str]
    filename: Optional[str]
    publish_date: Optional[str]
    page_number: Optional[int]
    score: Optional[float]
    content_snippet: str


class DocumentSearchResult(BaseModel):
    query: str
    search_mode: str
    total_pages_matched: int
    total_documents: int
    documents: list[DocumentSearchHit]


def _meta(request: Request) -> ResponseMeta:
    return make_meta(
        request_id=request.state.request_id,
        execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
    )


@router.get(
    "/documents/search",
    response_model=SuccessResponse[DocumentSearchResult],
    summary="Pencarian Document yang sedang di indexing pada background task",
)
def search_document(
    request: Request,
    q: str = Query(..., min_length=1, description="Text untuk pencarian pada content dan filename"),
    size: int = Query(20, ge=1, le=100, description="Max documents untuk dikembalikan"),
    from_: int = Query(0, ge=0, alias="from", description="Pagination offset"),
) -> SuccessResponse[DocumentSearchResult]:
    """
    Search indexed documents in Elasticsearch.
    Results are collapsed by document_id (one row per document, best matching page).
    """
    logger.info("search_document q=%s size=%s from=%s", q, size, from_)

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
    except Exception as exc:
        logger.exception("Search failed q=%s", q)
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            "Pencarian gagal.",
            details={"error": str(exc)},
        ) from exc

    return SuccessResponse[DocumentSearchResult](
        data=DocumentSearchResult(**raw),
        meta=_meta(request),
    )


@router.get(
    "/documents/download/{document_id}",
    summary="Download document file yang sudah diindexing",
    responses={200: {"content": {"application/pdf": {}}}},
)
def download_document(
    document_id: str,
    session: Session = Depends(get_session),
):
    """
    Download the archived file from storage (raw PDF).
    Only allowed when status is ``indexed``.
    """
    doc = get_document_by_document_id(session, document_id)
    if doc is None:
        raise ApiError(
            ErrorCode.ARSIP_NOT_FOUND,
            f"Dokumen dengan document_id '{document_id}' tidak ditemukan.",
            details={"document_id": document_id},
        )

    if doc.status != DOCUMENT_STATUS_INDEXED:
        raise ApiError(
            ErrorCode.DOCUMENT_NOT_INDEXED,
            f"Dokumen belum siap diunduh (status={doc.status}).",
            details={"document_id": document_id, "status": doc.status},
        )

    file_path = resolve_document_file(
        doc.document_id,
        doc.filename,
        doc.created_at,
    )
    if not file_path.is_file():
        raise ApiError(
            ErrorCode.DOCUMENT_FILE_MISSING,
            "File dokumen tidak ditemukan di storage.",
            details={"document_id": document_id},
        )

    logger.info("download document_id=%s path=%s", document_id, file_path)
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=Path(doc.filename).name,
    )


@router.get(
    "/documents/{document_id}",
    response_model=SuccessResponse[Document],
    summary="Mengambil status dokumen berdasarkan document_id",
)
def get_document(
    document_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> SuccessResponse[Document]:
    doc = get_document_by_document_id(session, document_id)
    if doc is None:
        raise ApiError(
            ErrorCode.ARSIP_NOT_FOUND,
            f"Dokumen dengan document_id '{document_id}' tidak ditemukan.",
            details={"document_id": document_id},
        )
    return SuccessResponse[Document](data=doc, meta=_meta(request))


@router.post(
    "/upload",
    response_model=SuccessResponse[DocumentUploadAccepted],
    status_code=202,
    summary="Upload document untuk background indexing",
)
async def upload_document(
    request: Request,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> SuccessResponse[DocumentUploadAccepted]:
    document_id = str(uuid.uuid4())
    logger.info("upload_document document_id=%s", document_id)
    temp_file_path = f"temp_{document_id}_{file.filename}"

    with open(temp_file_path, "wb") as buffer:
        buffer.write(await file.read())

    if is_pdf_file(temp_file_path, file.filename):
        try:
            validate_pdf_for_upload(
                temp_file_path,
                MIN_PDF_TEXT_CHARS,
                require_text_layer=not TIKA_PDF_OCR_ENABLED,
            )
        except PdfValidationError as exc:
            os.remove(temp_file_path)
            code = _PDF_VALIDATION_TO_ERROR.get(exc.code, ErrorCode.PDF_NOT_READABLE)
            raise ApiError(
                code,
                exc.message,
                details={"validation_code": exc.code, "filename": file.filename},
            ) from exc

    create_document(session, document_id=document_id, filename=file.filename or "")
    logger.info(
        "Upload diterima, queueing background task dengan document_id=%s file=%s",
        document_id,
        file.filename,
    )

    background_tasks.add_task(
        process_and_index_pdf,
        file_path=temp_file_path,
        document_id=document_id,
        original_filename=file.filename,
    )

    return SuccessResponse[DocumentUploadAccepted](
        data=DocumentUploadAccepted(
            message="File diterima dan sedang diproses di background.",
            document_id=document_id,
            filename=file.filename,
            status="processing",
        ),
        meta=_meta(request),
    )
