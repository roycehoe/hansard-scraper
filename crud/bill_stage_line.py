from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from database.bill_stage_line import BillStageLine
from enums import BillStage


@dataclass(frozen=True)
class BillStageLineRow:
    id: int
    stage: BillStage
    printed_text: str
    ordinal: int
    sprs_report_id: str


class CRUDBillStageLine:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, bill_stage_lines: list[BillStageLine]) -> None:
        self.session.add_all(bill_stage_lines)
        self.session.flush()

    def get_rows(self) -> list[BillStageLineRow]:
        statement = select(
            BillStageLine.id,
            BillStageLine.stage,
            BillStageLine.printed_text,
            BillStageLine.ordinal,
            BillStageLine.sprs_report_id,
        ).order_by(
            BillStageLine.sprs_report_id, BillStageLine.ordinal, BillStageLine.stage
        )
        return [BillStageLineRow(*row) for row in self.session.exec(statement).all()]

    def get_rows_by_sprs_report_ids(
        self, sprs_report_ids: list[str]
    ) -> list[BillStageLineRow]:
        statement = (
            select(
                BillStageLine.id,
                BillStageLine.stage,
                BillStageLine.printed_text,
                BillStageLine.ordinal,
                BillStageLine.sprs_report_id,
            )
            .where(col(BillStageLine.sprs_report_id).in_(sprs_report_ids))
            .order_by(
                BillStageLine.sprs_report_id, BillStageLine.ordinal, BillStageLine.stage
            )
        )
        return [BillStageLineRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_sprs_report_ids(self, sprs_report_ids: list[str]) -> int:
        statement = delete(BillStageLine).where(
            col(BillStageLine.sprs_report_id).in_(sprs_report_ids)
        )

        return self.session.exec(statement).rowcount

    def delete_all(self) -> int:
        statement = delete(BillStageLine)

        return self.session.exec(statement).rowcount
