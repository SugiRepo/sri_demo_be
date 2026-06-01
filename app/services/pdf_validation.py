from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfValidationError(Exception):
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(message)


def is_pdf_file(file_path: str, filename: str | None = None) -> bool:
    """True if the upload should be treated as PDF (extension or %PDF header)."""
    if filename and filename.lower().endswith(".pdf"):
        return True
    with open(file_path, "rb") as f:
        return f.read(5).startswith(b"%PDF")


def validate_pdf_structure(file_path: str) -> None:
    """Ensure the file is a readable PDF (valid header and parseable)."""
    with open(file_path, "rb") as f:
        header = f.read(5)

    if not header.startswith(b"%PDF"):
        raise PdfValidationError("File is not a valid PDF.", "invalid_pdf")

    try:
        reader = PdfReader(file_path)
        if len(reader.pages) == 0:
            raise PdfValidationError("PDF has no pages.", "empty_pdf")
    except PdfReadError as e:
        raise PdfValidationError(
            f"PDF could not be read: {e}", "pdf_read_error"
        ) from e


def validate_pdf_has_text_layer(file_path: str, min_chars: int) -> None:
    """
    Ensure the PDF has enough embedded (selectable) text without OCR.
    Use only when Tika OCR is disabled.
    """
    reader = PdfReader(file_path)
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        total += len(text.strip())

    if total < min_chars:
        raise PdfValidationError(
            "PDF has no extractable text (image-only or scanned without a text layer).",
            "no_extractable_text",
        )


def validate_pdf_for_upload(
    file_path: str,
    min_chars: int,
    *,
    require_text_layer: bool = True,
) -> None:
    """
    Validate PDF at upload.

    - Always: valid PDF structure.
    - If require_text_layer=True (no OCR): reject image-only scans early via pypdf.
    - If require_text_layer=False (OCR enabled): allow scans; Tika+Tesseract extracts text later.
    """
    validate_pdf_structure(file_path)
    if require_text_layer:
        validate_pdf_has_text_layer(file_path, min_chars)
