import logging
import os
import time
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api_v1.envelope import SuccessResponse, make_meta
from app.api_v1.errors import ApiError, ErrorCode
from app.database import get_session
from app.models.watermark_document import WatermarkDocument
from app.services.pdf_validation import (
    PdfValidationError,
    is_pdf_file,
    validate_pdf_structure,
)
from app.services.watermark_db import (
    create_watermark_document,
    get_watermark_by_id,
    list_watermark_documents,
)
from app.services.watermark_process import process_watermark_pdf
from app.services.watermark_storage import (
    build_document_path,
    build_output_filename,
    resolve_output_file,
)

router = APIRouter(tags=["Watermarks"])
logger = logging.getLogger("app.routers.watermarks")


class WatermarkStampAccepted(BaseModel):
    message: str
    watermark_id: str
    file_name: str
    status: str = Field(default="processing")


class WatermarkListData(BaseModel):
    count: int
    items: list[WatermarkDocument]


@router.post(
    "/watermark-document/stamp",
    response_model=SuccessResponse[WatermarkStampAccepted],
    status_code=202,
    summary="Queue PDF watermark job",
)
async def generate_pdf_watermark(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    file: UploadFile = File(...),
    watermark: str = Form(..., min_length=1),
    filename: str | None = Form(None),
    opacity: float = Form(0.25, ge=0.05, le=1.0),
    angle: float = Form(45),
    create_by: str = Form("api"),
) -> SuccessResponse[WatermarkStampAccepted]:
    """
    Queue a PDF watermark job (PDF only). Poll status via GET /watermark-documents/{id};
    download when status is success.
    """
    upload_name = file.filename or "document.pdf"

    if not upload_name.lower().endswith(".pdf"):
        raise ApiError(
            ErrorCode.UNSUPPORTED_FILE,
            "Hanya file PDF yang diterima.",
            details={"filename": upload_name},
        )

    watermark_id = str(uuid.uuid4())
    stored_file_name = filename or upload_name
    document_path = build_document_path()
    file_name_output = build_output_filename(watermark_id, stored_file_name)
    temp_file_path = f"temp_{watermark_id}_{upload_name}"

    logger.info(
        "generate_pdf_watermark watermark_id=%s upload=%s",
        watermark_id,
        upload_name,
    )

    with open(temp_file_path, "wb") as buffer:
        buffer.write(await file.read())

    if not is_pdf_file(temp_file_path, upload_name):
        os.remove(temp_file_path)
        raise ApiError(
            ErrorCode.UNSUPPORTED_FILE,
            "File bukan PDF yang valid.",
            details={"filename": upload_name},
        )

    try:
        validate_pdf_structure(temp_file_path)
    except PdfValidationError as exc:
        os.remove(temp_file_path)
        raise ApiError(
            ErrorCode.PDF_NOT_READABLE,
            exc.message,
            details={"validation_code": exc.code, "filename": upload_name},
        ) from exc

    create_watermark_document(
        session,
        watermark_id=watermark_id,
        file_name=stored_file_name,
        document_path=document_path,
        file_name_output=file_name_output,
        watermark_wording=watermark,
        create_by=create_by,
    )

    background_tasks.add_task(
        process_watermark_pdf,
        temp_file_path=temp_file_path,
        watermark_id=watermark_id,
        watermark_wording=watermark,
        document_path=document_path,
        file_name_output=file_name_output,
        opacity=opacity,
        angle=angle,
    )

    return SuccessResponse[WatermarkStampAccepted](
        data=WatermarkStampAccepted(
            message="Watermark job accepted.",
            watermark_id=watermark_id,
            file_name=stored_file_name,
            status="processing",
        ),
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )


@router.get(
    "/watermark-documents",
    response_model=SuccessResponse[WatermarkListData],
    summary="List watermark jobs",
)
def list_watermark_documents_endpoint(
    request: Request,
    session: Session = Depends(get_session),
    watermark_id: str | None = Query(None, description="Filter by exact watermark_id"),
    file_name: str | None = Query(None, description="Filter by file_name (contains)"),
) -> SuccessResponse[WatermarkListData]:
    rows = list_watermark_documents(
        session,
        watermark_id=watermark_id,
        file_name=file_name,
    )
    return SuccessResponse[WatermarkListData](
        data=WatermarkListData(count=len(rows), items=rows),
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )


@router.get(
    "/watermark-documents/{watermark_id}",
    response_model=SuccessResponse[WatermarkDocument],
    summary="Pencarian watermark job berdasarkan watermark_id",
)
def get_watermark_document(
    watermark_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> SuccessResponse[WatermarkDocument]:
    row = get_watermark_by_id(session, watermark_id)
    if row is None:
        raise ApiError(
            ErrorCode.WATERMARK_NOT_FOUND,
            f"Watermark dengan id '{watermark_id}' tidak ditemukan.",
            details={"watermark_id": watermark_id},
        )
    return SuccessResponse[WatermarkDocument](
        data=row,
        meta=make_meta(
            request_id=request.state.request_id,
            execution_time_ms=(time.perf_counter() - request.state.start_time) * 1000,
        ),
    )


@router.get(
    "/watermark-documents/{watermark_id}/download",
    summary="Download watermarked PDF",
    responses={200: {"content": {"application/pdf": {}}}},
)
def download_watermark_document(
    watermark_id: str,
    session: Session = Depends(get_session),
):
    """Returns raw PDF bytes (not JSON envelope)."""
    row = get_watermark_by_id(session, watermark_id)
    if row is None:
        raise ApiError(
            ErrorCode.WATERMARK_NOT_FOUND,
            f"Watermark dengan id '{watermark_id}' tidak ditemukan.",
            details={"watermark_id": watermark_id},
        )

    if row.status != "success":
        raise ApiError(
            ErrorCode.WATERMARK_NOT_READY,
            f"Dokumen belum siap diunduh (status={row.status}).",
            details={"watermark_id": watermark_id, "status": row.status},
        )

    file_path = resolve_output_file(row.document_path, row.file_name_output)
    if not file_path.is_file():
        raise ApiError(
            ErrorCode.WATERMARK_FILE_MISSING,
            "File watermark tidak ditemukan di storage.",
            details={
                "watermark_id": watermark_id,
                "document_path": row.document_path,
                "file_name_output": row.file_name_output,
            },
        )

    logger.info("download watermark_id=%s path=%s", watermark_id, file_path)
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=row.file_name_output,
    )
