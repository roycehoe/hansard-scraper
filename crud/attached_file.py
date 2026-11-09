from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session, col, select

from database.attached_file import AttachedFile
from enums import AttachedFileKind


@dataclass(frozen=True)
class AttachedFileRow:
    id: int
    download_value: str


@dataclass(frozen=True)
class AttachedFileKeyRow:
    sitting_id: int
    kind: AttachedFileKind
    sprs_file_id: int
    download_value: Optional[str]
    printed_title: str


class CRUDAttachedFile:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, attached_files: list[AttachedFile]) -> None:
        self.session.add_all(attached_files)
        self.session.flush()

    def get_rows_by_download_values(
        self, download_values: list[str]
    ) -> list[AttachedFileRow]:
        statement = select(AttachedFile.id, AttachedFile.download_value).where(
            col(AttachedFile.download_value).in_(download_values)
        )
        return [AttachedFileRow(*row) for row in self.session.exec(statement).all()]

    def get_key_rows(self) -> list[AttachedFileKeyRow]:
        statement = select(
            AttachedFile.sitting_id,
            AttachedFile.kind,
            AttachedFile.sprs_file_id,
            AttachedFile.download_value,
            AttachedFile.printed_title,
        )
        return [AttachedFileKeyRow(*row) for row in self.session.exec(statement).all()]

    def get_by_ids(self, attached_file_ids: list[int]) -> list[AttachedFile]:
        statement = (
            select(AttachedFile)
            .where(col(AttachedFile.id).in_(attached_file_ids))
            .order_by(AttachedFile.id)
        )
        return list(self.session.exec(statement).all())

    def get_by_sitting_ids(self, sitting_ids: list[int]) -> list[AttachedFile]:
        statement = (
            select(AttachedFile)
            .where(col(AttachedFile.sitting_id).in_(sitting_ids))
            .order_by(AttachedFile.id)
        )
        return list(self.session.exec(statement).all())
