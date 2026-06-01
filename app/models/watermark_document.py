from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WatermarkDocument(SQLModel, table=True):
    __tablename__ = "watermark_document"

    watermark_id: str = Field(primary_key=True, max_length=36)
    file_name: str = Field(max_length=512, index=True)
    document_path: str = Field(max_length=512)
    file_name_output: str = Field(max_length=512)
    number_of_page: Optional[int] = Field(default=None)
    watermark_wording: str = Field(max_length=2000)
    status: str = Field(default="processing", max_length=32, index=True)
    create_by: str = Field(max_length=128)
    create_date: datetime = Field(default_factory=utc_now)
    change_by: str = Field(max_length=128)
    change_date: datetime = Field(default_factory=utc_now)
