import logging

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.api_v1.errors import ApiError, ErrorCode
from app.schemas.generate_pdf import GeneratePdfImageRequest
from app.services.pdf_image_generate import build_pdf_from_image_pages

router = APIRouter(tags=["Generate"])
logger = logging.getLogger("app.routers.generate")


def _pdf_download_filename(name: str | None, fallback: str) -> str:
    base = name or fallback
    return base if base.lower().endswith(".pdf") else f"{base}.pdf"


@router.post(
    "/generate/pdf-image",
    summary="Buat image-only PDF untuk pengujian OCR/upload",
    responses={200: {"content": {"application/pdf": {}}}},
)
def generate_pdf_image(
    body: GeneratePdfImageRequest,
    request: Request,
) -> Response:
    """
    Build a PDF where each page is a raster image of the given text (no text layer).
    Returns the file as a download — useful for OCR / upload testing.

    Success: raw PDF bytes (not JSON envelope). Errors: ApiError envelope.
    """
    logger.info(
        "generate_pdf_image filename=%s pages=%s request_id=%s",
        body.filename,
        len(body.pages),
        request.state.request_id,
    )
    try:
        pdf_bytes = build_pdf_from_image_pages(body.pages)
    except Exception as exc:
        logger.exception("generate_pdf_image failed")
        raise ApiError(
            ErrorCode.PDF_GENERATE_FAILED,
            "Gagal membuat PDF dari halaman gambar.",
            details={"error": str(exc)},
        ) from exc

    filename = _pdf_download_filename(body.filename, "generated-test.pdf")
    logger.info(
        "generate_pdf_image ok filename=%s bytes=%s",
        filename,
        len(pdf_bytes),
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
