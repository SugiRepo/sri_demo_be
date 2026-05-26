from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: str = Field(index=True, unique=True, max_length=36)
    filename: str = Field(max_length=512)
    status: str = Field(default="processing", max_length=32, index=True)
    page_count: Optional[int] = Field(default=None)
    error_message: Optional[str] = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
