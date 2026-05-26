from datetime import datetime, timezone

from sqlmodel import Session, select

from app.database import engine
from app.models.document import Document


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_document(session: Session, document_id: str, filename: str) -> Document:
    doc = Document(document_id=document_id, filename=filename, status="processing")
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def get_document_by_document_id(
    session: Session, document_id: str
) -> Document | None:
    statement = select(Document).where(Document.document_id == document_id)
    return session.exec(statement).first()


def update_document_status(
    session: Session,
    document_id: str,
    status: str,
    *,
    page_count: int | None = None,
    error_message: str | None = None,
) -> Document | None:
    doc = get_document_by_document_id(session, document_id)
    if doc is None:
        return None

    doc.status = status
    doc.updated_at = utc_now()
    if page_count is not None:
        doc.page_count = page_count
    if error_message is not None:
        doc.error_message = error_message

    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def delete_document(session: Session, document_id: str) -> bool:
    doc = get_document_by_document_id(session, document_id)
    if doc is None:
        return False

    session.delete(doc)
    session.commit()
    return True


def update_document_status_in_background(
    document_id: str,
    status: str,
    *,
    page_count: int | None = None,
    error_message: str | None = None,
) -> None:
    """Use a fresh session for FastAPI background tasks."""
    with Session(engine) as session:
        update_document_status(
            session,
            document_id,
            status,
            page_count=page_count,
            error_message=error_message,
        )
