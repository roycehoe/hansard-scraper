from dataclasses import dataclass
from typing import Optional

import sqlalchemy
from sqlalchemy import delete, update
from sqlmodel import Session, col, func, select

from database.report_picture import ReportPicture
from enums import PictureKind
from utils.report_picture_update import ReportPictureUpdate


@dataclass(frozen=True)
class ReportPictureRow:
    id: int
    kind: PictureKind
    picture_index: int
    content_offset: int
    follows_ordinal: Optional[int]
    sha256: str
    typed_copy: Optional[dict[str, object]]
    report_id: int


class CRUDReportPicture:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, report_pictures: list[ReportPicture]) -> None:
        self.session.add_all(report_pictures)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(ReportPicture)
        return self.session.exec(statement).one()

    def get_rows(self) -> list[ReportPictureRow]:
        statement = sqlalchemy.select(
            col(ReportPicture.id),
            col(ReportPicture.kind),
            col(ReportPicture.picture_index),
            col(ReportPicture.content_offset),
            col(ReportPicture.follows_ordinal),
            col(ReportPicture.sha256),
            col(ReportPicture.typed_copy),
            col(ReportPicture.report_id),
        ).order_by(col(ReportPicture.id))
        return [ReportPictureRow(*row) for row in self.session.execute(statement).all()]

    def update_many(self, report_picture_updates: list[ReportPictureUpdate]) -> None:
        if not report_picture_updates:
            return
        self.session.execute(
            update(ReportPicture),
            [
                {
                    "id": report_picture_update.id,
                    "kind": report_picture_update.kind,
                    "content_offset": report_picture_update.content_offset,
                    "follows_ordinal": report_picture_update.follows_ordinal,
                    "typed_copy": report_picture_update.typed_copy,
                }
                for report_picture_update in report_picture_updates
            ],
        )

    def delete_by_ids(self, report_picture_ids: list[int]) -> None:
        if not report_picture_ids:
            return

        statement = delete(ReportPicture).where(
            col(ReportPicture.id).in_(report_picture_ids)
        )
        self.session.execute(statement)
