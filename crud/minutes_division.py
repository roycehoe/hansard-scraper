from dataclasses import dataclass
from typing import Optional

from sqlalchemy import update
from sqlmodel import Session, col, delete, select

from database.minutes_division import MinutesDivision
from enums import DivisionListStatus, MinutesDivisionPairing


@dataclass(frozen=True)
class MinutesDivisionRow:
    minutes_id: int
    ordinal: int
    printed_counts: str
    ayes: int
    noes: int
    abstentions: Optional[int]
    list_status: DivisionListStatus
    pairing: MinutesDivisionPairing
    division_id: int


class CRUDMinutesDivision:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, minutes_divisions: list[MinutesDivision]) -> None:
        self.session.add_all(minutes_divisions)
        self.session.flush()

    def get_rows_by_minutes_ids(
        self, minutes_ids: list[int]
    ) -> list[MinutesDivisionRow]:
        statement = (
            select(
                MinutesDivision.minutes_id,
                MinutesDivision.ordinal,
                MinutesDivision.printed_counts,
                MinutesDivision.ayes,
                MinutesDivision.noes,
                MinutesDivision.abstentions,
                MinutesDivision.list_status,
                MinutesDivision.pairing,
                MinutesDivision.division_id,
            )
            .where(col(MinutesDivision.minutes_id).in_(minutes_ids))
            .order_by(MinutesDivision.minutes_id, MinutesDivision.ordinal)
        )
        return [MinutesDivisionRow(*row) for row in self.session.exec(statement).all()]

    def get_rows_by_division_ids(
        self, division_ids: list[int]
    ) -> list[MinutesDivisionRow]:
        statement = (
            select(
                MinutesDivision.minutes_id,
                MinutesDivision.ordinal,
                MinutesDivision.printed_counts,
                MinutesDivision.ayes,
                MinutesDivision.noes,
                MinutesDivision.abstentions,
                MinutesDivision.list_status,
                MinutesDivision.pairing,
                MinutesDivision.division_id,
            )
            .where(col(MinutesDivision.division_id).in_(division_ids))
            .order_by(MinutesDivision.minutes_id, MinutesDivision.ordinal)
        )
        return [MinutesDivisionRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_minutes_ids(self, minutes_ids: list[int]) -> int:
        statement = delete(MinutesDivision).where(
            col(MinutesDivision.minutes_id).in_(minutes_ids)
        )

        return self.session.exec(statement).rowcount

    def delete_by_division_ids(self, division_ids: list[int]) -> int:
        statement = delete(MinutesDivision).where(
            col(MinutesDivision.division_id).in_(division_ids)
        )

        return self.session.exec(statement).rowcount

    def set_pairing_by_division_ids(
        self, division_ids: list[int], pairing: MinutesDivisionPairing
    ) -> int:
        statement = (
            update(MinutesDivision)
            .where(col(MinutesDivision.division_id).in_(division_ids))
            .values(pairing=pairing)
        )

        return self.session.execute(statement).rowcount
