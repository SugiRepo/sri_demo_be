"""
Apply a diagonal text watermark to every page of a PDF.
"""

from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas


def _font_size_for_watermark(
    page_width: float,
    page_height: float,
    watermark_text: str,
) -> float:
    base = min(page_width, page_height) * 0.08
    size = min(72.0, max(18.0, base))
    if len(watermark_text) > 20:
        size *= max(0.45, 20 / len(watermark_text))
    return size


def _build_overlay_page(
    page_width: float,
    page_height: float,
    watermark_text: str,
    *,
    opacity: float,
    angle: float,
):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))

    pdf.saveState()
    pdf.setFillColor(Color(0, 0, 0, alpha=opacity))
    font_size = _font_size_for_watermark(page_width, page_height, watermark_text)
    pdf.setFont("Helvetica-Bold", font_size)
    pdf.translate(page_width / 2, page_height / 2)
    pdf.rotate(angle)
    pdf.drawCentredString(0, 0, watermark_text)
    pdf.restoreState()

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def apply_watermark_to_pdf(
    pdf_bytes: bytes,
    watermark_text: str,
    *,
    opacity: float = 0.25,
    angle: float = 45,
) -> bytes:
    """Return a new PDF with diagonal centered watermark on each page."""
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()

    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        overlay = _build_overlay_page(
            width,
            height,
            watermark_text,
            opacity=opacity,
            angle=angle,
        )
        page.merge_page(overlay)
        writer.add_page(page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
