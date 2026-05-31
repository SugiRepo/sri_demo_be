import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import INDEX_NAME, es
from app.services.metadata_extraction import ExtractionResult, extract_metadata

router = APIRouter(prefix="/metadata", tags=["Metadata Extraction"])
logger = logging.getLogger("app.routers.metadata")


class ExtractTextRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=10,
        max_length=200_000,
        description="Teks naskah dinas yang akan diekstrak metadatanya.",
    )


class ExtractByDocumentResult(BaseModel):
    document_id: str
    filename: str | None = None
    page_used: int
    extraction: ExtractionResult


@router.post(
    "/extract",
    response_model=ExtractionResult,
    summary="Ekstrak metadata dari teks naskah dinas (Layer 1: regex)",
)
def extract_from_text(payload: ExtractTextRequest) -> ExtractionResult:
    """
    Layer 1 ekstraksi metadata: rule-based regex.

    Cocok untuk field strict-format pada naskah dinas pemerintah Indonesia:
    Nomor, Sifat, Lampiran, Perihal, Tempat, Tanggal, Yth., Klasifikasi, NIP.

    Field free-form (Pengirim, Jabatan, Penerima detail) sebaiknya
    di-fallback ke Layer 2 (NER mini-model fine-tuned, mis. IndoBERT).
    """
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Teks kosong.")

    try:
        result = extract_metadata(payload.text)
    except Exception as exc:
        logger.exception("Ekstraksi metadata gagal")
        raise HTTPException(
            status_code=500,
            detail={"message": "Ekstraksi gagal", "error": str(exc)},
        ) from exc

    logger.info(
        "Metadata extract len=%d filled=%d/%d conf=%.2f",
        result.text_length,
        result.fields_filled,
        result.fields_total,
        result.overall_confidence,
    )
    return result


def _fetch_document_first_page(document_id: str) -> tuple[str, str | None, int]:
    """Cari halaman pertama (page_number terkecil) dokumen di Elasticsearch."""
    try:
        response = es.search(
            index=INDEX_NAME,
            query={"term": {"document_id": document_id}},
            sort=[{"page_number": "asc"}],
            size=1,
            _source=["filename", "content", "page_number"],
        )
    except Exception as exc:
        logger.exception("Gagal query Elasticsearch document_id=%s", document_id)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "elasticsearch_unavailable",
                "message": f"Tidak bisa mengambil dokumen dari Elasticsearch: {exc}",
            },
        ) from exc

    hits = response.get("hits", {}).get("hits", [])
    if not hits:
        raise HTTPException(
            status_code=404,
            detail=f"Dokumen dengan document_id '{document_id}' tidak ditemukan di index.",
        )

    source = hits[0].get("_source", {})
    content = source.get("content") or ""
    filename = source.get("filename")
    page_number = int(source.get("page_number") or 1)

    if not content.strip():
        raise HTTPException(
            status_code=422,
            detail="Halaman pertama dokumen kosong / tidak punya teks untuk diekstrak.",
        )

    return content, filename, page_number


@router.get(
    "/extract/by-document/{document_id}",
    response_model=ExtractByDocumentResult,
    summary="Ekstrak metadata dari dokumen yang sudah terindeks (by document_id)",
)
def extract_by_document(document_id: str) -> ExtractByDocumentResult:
    """
    Retrofit ekstraksi pada dokumen yang sudah ada di Elasticsearch index.
    Menggunakan teks halaman pertama (page_number terkecil) sebagai input.
    """
    content, filename, page_number = _fetch_document_first_page(document_id)
    result = extract_metadata(content)
    logger.info(
        "Metadata extract by-document=%s page=%d filled=%d/%d conf=%.2f",
        document_id,
        page_number,
        result.fields_filled,
        result.fields_total,
        result.overall_confidence,
    )
    return ExtractByDocumentResult(
        document_id=document_id,
        filename=filename,
        page_used=page_number,
        extraction=result,
    )
