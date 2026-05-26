import logging
import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from sqlmodel import Session

from app.config import MIN_PDF_TEXT_CHARS
from app.database import get_session
from app.services.document_db import create_document, get_document_by_document_id
from app.services.document_search import (
    ElasticsearchConnectionError,
    ElasticsearchSearchError,
    search_documents,
)
from app.services.pdf_ingest import process_and_index_pdf
from app.services.pdf_validation import (
    PdfValidationError,
    is_pdf_file,
    validate_pdf_for_upload,
)

router = APIRouter(tags=["Documents"])
logger = logging.getLogger("app.routers.documents")


@router.get("/documents/search")
def search_document(
    q: str = Query(..., min_length=1, description="Text to search in content and filename"),
    size: int = Query(20, ge=1, le=100, description="Max documents to return"),
    from_: int = Query(0, ge=0, alias="from", description="Pagination offset"),
):
    """
    Search indexed documents in Elasticsearch.
    Results are collapsed by document_id (one row per document, best matching page).
    """
    logger.info(f"search_document q: {q} size: {size} from: {from_}")

    try:
        return search_documents(q, size=size, from_=from_)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ElasticsearchConnectionError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "elasticsearch_unavailable",
                "message": e.message,
            },
        ) from e
    except ElasticsearchSearchError as e:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "elasticsearch_search_error",
                "message": e.message,
            },
        ) from e
    except Exception as e:
        logger.exception("Search failed q=%s", q)
        raise HTTPException(
            status_code=502,
            detail={"message": "Search failed", "error": str(e)},
        ) from e


@router.get("/documents/{document_id}")
def get_document(document_id: str, session: Session = Depends(get_session)):
    doc = get_document_by_document_id(session, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/upload")
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    document_id = str(uuid.uuid4())
    logger.info("upload_document document_id=%s", document_id)
    temp_file_path = f"temp_{document_id}_{file.filename}"

    with open(temp_file_path, "wb") as buffer:
        buffer.write(await file.read())

    if is_pdf_file(temp_file_path, file.filename):
        logger.info(f"is_pdf_file: True")
        try:
            validate_pdf_for_upload(temp_file_path, MIN_PDF_TEXT_CHARS)
        except PdfValidationError as e:
            os.remove(temp_file_path)
            raise HTTPException(
                status_code=400,
                detail={"code": e.code, "message": e.message},
            ) from e

    create_document(session, document_id=document_id, filename=file.filename or "")
    logger.info(
        "Upload accepted, queueing background task document_id=%s file=%s",
        document_id,
        file.filename,
    )

    background_tasks.add_task(
        process_and_index_pdf,
        file_path=temp_file_path,
        document_id=document_id,
        original_filename=file.filename,
    )

    return {
        "message": "File received and is processing in the background.",
        "document_id": document_id,
        "filename": file.filename,
        "status": "processing",
    }
