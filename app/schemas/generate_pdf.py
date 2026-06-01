from pydantic import BaseModel, Field


class PdfImagePageInput(BaseModel):
    """One page: text is drawn onto an image (no PDF text layer)."""

    page: int = Field(ge=1, description="Page number (used for ordering)")
    content: str = Field(min_length=1, description="Text rendered as image on this page")


class GeneratePdfImageRequest(BaseModel):
    filename: str = Field(
        default="generated-test.pdf",
        description="Download filename",
    )
    pages: list[PdfImagePageInput] = Field(
        min_length=1,
        description="One or more pages with content",
    )
