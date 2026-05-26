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


def _count_extractable_chars(file_path: str) -> int:
    reader = PdfReader(file_path)
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        total += len(text.strip())
    return total


def validate_pdf_for_upload(file_path: str, min_chars: int) -> None:
    """
    Ensure the file is a readable PDF with an embedded text layer.
    Image-only / scanned PDFs (no selectable text) are rejected.
    """
    with open(file_path, "rb") as f:
        header = f.read(5)

    if not header.startswith(b"%PDF"):
        raise PdfValidationError("File is not a valid PDF.", "invalid_pdf")

    try:
        char_count = _count_extractable_chars(file_path)
    except PdfReadError as e:
        raise PdfValidationError(
            f"PDF could not be read: {e}", "pdf_read_error"
        ) from e

    if char_count < min_chars:
        raise PdfValidationError(
            "PDF has no extractable text (image-only or scanned without a text layer).",
            "no_extractable_text",
        )
