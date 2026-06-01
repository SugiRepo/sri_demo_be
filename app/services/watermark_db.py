from datetime import datetime, timezone

from sqlmodel import Session, col, select

from app.database import engine
from app.models.watermark_document import WatermarkDocument


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_watermark_document(
    session: Session,
    *,
    watermark_id: str,
    file_name: str,
    document_path: str,
    file_name_output: str,
    watermark_wording: str,
    create_by: str,
) -> WatermarkDocument:
    now = utc_now()
    row = WatermarkDocument(
        watermark_id=watermark_id,
        file_name=file_name,
        document_path=document_path,
        file_name_output=file_name_output,
        watermark_wording=watermark_wording,
        status="processing",
        create_by=create_by,
        create_date=now,
        change_by=create_by,
        change_date=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_watermark_by_id(
    session: Session,
    watermark_id: str,
) -> WatermarkDocument | None:
    return session.get(WatermarkDocument, watermark_id)


def list_watermark_documents(
    session: Session,
    *,
    watermark_id: str | None = None,
    file_name: str | None = None,
) -> list[WatermarkDocument]:
    statement = select(WatermarkDocument).order_by(col(WatermarkDocument.create_date).desc())

    if watermark_id:
        statement = statement.where(WatermarkDocument.watermark_id == watermark_id)
    if file_name:
        pattern = f"%{file_name}%"
        statement = statement.where(col(WatermarkDocument.file_name).ilike(pattern))

    return list(session.exec(statement).all())


def update_watermark_status(
    session: Session,
    watermark_id: str,
    status: str,
    *,
    number_of_page: int | None = None,
    change_by: str = "system",
) -> WatermarkDocument | None:
    row = get_watermark_by_id(session, watermark_id)
    if row is None:
        return None

    row.status = status
    row.change_by = change_by
    row.change_date = utc_now()
    if number_of_page is not None:
        row.number_of_page = number_of_page

    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def update_watermark_in_background(
    watermark_id: str,
    status: str,
    *,
    number_of_page: int | None = None,
    change_by: str = "system",
) -> None:
    with Session(engine) as session:
        update_watermark_status(
            session,
            watermark_id,
            status,
            number_of_page=number_of_page,
            change_by=change_by,
        )
