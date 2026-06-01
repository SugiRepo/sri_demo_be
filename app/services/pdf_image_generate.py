"""
Build PDFs where each page is a full-page raster image (no selectable text layer).
Useful for testing upload + Tika OCR pipelines.
"""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.schemas.generate_pdf import PdfImagePageInput

# A4 in points (reportlab); raster at ~150 DPI for readable OCR
PAGE_WIDTH_PT, PAGE_HEIGHT_PT = A4
IMAGE_WIDTH_PX = int(PAGE_WIDTH_PT * 150 / 72)
IMAGE_HEIGHT_PX = int(PAGE_HEIGHT_PT * 150 / 72)
MARGIN_PX = 40
LINE_SPACING = 8


def _load_font(size: int = 28) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = text.replace("\r\n", "\n").replace("\r", "\n").split()
    if not words:
        return [""]

    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word]) if current else word
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def _render_page_image(content: str) -> BytesIO:
    img = Image.new("RGB", (IMAGE_WIDTH_PX, IMAGE_HEIGHT_PX), "white")
    draw = ImageDraw.Draw(img)
    font = _load_font()
    max_width = IMAGE_WIDTH_PX - 2 * MARGIN_PX
    y = MARGIN_PX

    for paragraph in content.split("\n"):
        for line in _wrap_lines(draw, paragraph, font, max_width):
            draw.text((MARGIN_PX, y), line, fill="black", font=font)
            bbox = draw.textbbox((MARGIN_PX, y), line, font=font)
            y = bbox[3] + LINE_SPACING
            if y > IMAGE_HEIGHT_PX - MARGIN_PX:
                break

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def build_pdf_from_image_pages(pages: list[PdfImagePageInput]) -> bytes:
    """Return PDF bytes; each input page becomes one full-page embedded image."""
    ordered = sorted(pages, key=lambda p: p.page)
    out = BytesIO()
    pdf = canvas.Canvas(out, pagesize=A4)

    for page in ordered:
        img_buf = _render_page_image(page.content)
        pdf.drawImage(
            ImageReader(img_buf),
            0,
            0,
            width=PAGE_WIDTH_PT,
            height=PAGE_HEIGHT_PT,
            preserveAspectRatio=True,
            anchor="sw",
        )
        pdf.showPage()

    pdf.save()
    return out.getvalue()
