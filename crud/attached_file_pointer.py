from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlmodel import Session, col, delete, func, select

from database.attached_file_pointer import AttachedFilePointer
from enums import AttachedFilePointerShape, ParagraphTieRule
from utils.attached_file_tie import AttachedFilePointerTie


@dataclass(frozen=True)
class AttachedFilePointerRow:
    sprs_report_id: str
    ordinal: int
    printed_text: str
    href: str
    shape: AttachedFilePointerShape
    download_value: Optional[str]
    speech_ordinal: Optional[int]
    paragraph_tie_rule: Optional[ParagraphTieRule]


@dataclass(frozen=True)
class AttachedFilePointerUntiedRow:
    id: int
    download_value: str


class CRUDAttachedFilePointer:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, attached_file_pointers: list[AttachedFilePointer]) -> None:
        self.session.add_all(attached_file_pointers)
        self.session.flush()

    def get_rows_by_sprs_report_ids(
        self, sprs_report_ids: list[str]
    ) -> list[AttachedFilePointerRow]:
        statement = (
            select(
                AttachedFilePointer.sprs_report_id,
                AttachedFilePointer.ordinal,
                AttachedFilePointer.printed_text,
                AttachedFilePointer.href,
                AttachedFilePointer.shape,
                AttachedFilePointer.download_value,
                AttachedFilePointer.speech_ordinal,
                AttachedFilePointer.paragraph_tie_rule,
            )
            .where(col(AttachedFilePointer.sprs_report_id).in_(sprs_report_ids))
            .order_by(AttachedFilePointer.sprs_report_id, AttachedFilePointer.ordinal)
        )
        return [
            AttachedFilePointerRow(*row) for row in self.session.exec(statement).all()
        ]

    def get_untied_rows_by_download_values_and_attached_file_id_null(
        self, download_values: list[str]
    ) -> list[AttachedFilePointerUntiedRow]:
        statement = (
            select(AttachedFilePointer.id, AttachedFilePointer.download_value)
            .where(col(AttachedFilePointer.attached_file_id).is_(None))
            .where(col(AttachedFilePointer.download_value).in_(download_values))
        )
        return [
            AttachedFilePointerUntiedRow(*row)
            for row in self.session.exec(statement).all()
        ]

    def set_attached_file_ids_bulk(self, ties: list[AttachedFilePointerTie]) -> int:
        if not ties:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE attached_file_pointer "
                "SET attached_file_id = v.attached_file_id "
                "FROM UNNEST(:attached_file_pointer_ids, :attached_file_ids) "
                "AS v(id, attached_file_id) "
                "WHERE attached_file_pointer.id = v.id"
            ),
            {
                "attached_file_pointer_ids": [
                    tie.attached_file_pointer_id for tie in ties
                ],
                "attached_file_ids": [tie.attached_file_id for tie in ties],
            },
        )

        return update_result.rowcount

    def get_count_by_sprs_report_ids_and_attached_file_id_not_null(
        self, sprs_report_ids: list[str]
    ) -> int:
        statement = (
            select(func.count())
            .select_from(AttachedFilePointer)
            .where(col(AttachedFilePointer.sprs_report_id).in_(sprs_report_ids))
            .where(col(AttachedFilePointer.attached_file_id).is_not(None))
        )
        return self.session.exec(statement).one()

    def delete_by_sprs_report_ids(self, sprs_report_ids: list[str]) -> int:
        statement = delete(AttachedFilePointer).where(
            col(AttachedFilePointer.sprs_report_id).in_(sprs_report_ids)
        )

        return self.session.exec(statement).rowcount
