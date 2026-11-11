from dataclasses import dataclass
from datetime import date

from sqlalchemy import Integer, text, update
from sqlmodel import Session, col, delete, func, select

from database.seat_holding import SeatHolding
from database.speaker import Speaker
from utils.seat_holding_update import SeatHoldingUpdate

_REPLACE_ALL = "g"
_CASE_INSENSITIVE = "i"
_YEARS_IN_DECADE = 10


@dataclass(frozen=True)
class SeatHoldingDecadeCount:
    decade: int
    seat_holding_count: int


@dataclass(frozen=True)
class SeatHoldingCheckRow:
    id: int
    division_key: str
    location_name: str
    first_sitting_date: date
    last_sitting_date: date
    sitting_count: int
    speaker_id: int
    speaker_name: str


class CRUDSeatHolding:
    def __init__(self, session: Session):
        self.session = session

    def lock_table_in_share_row_exclusive_mode(self) -> None:
        statement = text("LOCK TABLE seat_holding IN SHARE ROW EXCLUSIVE MODE")

        self.session.execute(statement)

    def add_many(self, seat_holdings: list[SeatHolding]) -> None:
        self.session.add_all(seat_holdings)
        self.session.flush()

    def get_by_speaker_ids(self, speaker_ids: list[int]) -> list[SeatHolding]:
        statement = select(SeatHolding).where(
            col(SeatHolding.speaker_id).in_(speaker_ids)
        )
        return list(self.session.exec(statement).all())

    def get_distinct_speaker_ids(self) -> list[int]:
        statement = select(SeatHolding.speaker_id).distinct()
        return list(self.session.exec(statement).all())

    def update_many(self, seat_holding_updates: list[SeatHoldingUpdate]) -> None:
        if not seat_holding_updates:
            return

        self.session.execute(
            update(SeatHolding),
            [
                {
                    "id": seat_holding_update.id,
                    "first_sitting_date": seat_holding_update.first_sitting_date,
                    "last_sitting_date": seat_holding_update.last_sitting_date,
                    "sitting_count": seat_holding_update.sitting_count,
                }
                for seat_holding_update in seat_holding_updates
            ],
        )
        self.session.flush()

    def get_check_rows(self) -> list[SeatHoldingCheckRow]:
        statement = (
            select(
                SeatHolding.id,
                SeatHolding.division_key,
                SeatHolding.location_name,
                SeatHolding.first_sitting_date,
                SeatHolding.last_sitting_date,
                SeatHolding.sitting_count,
                SeatHolding.speaker_id,
                Speaker.name,
            )
            .join(Speaker, col(Speaker.id) == col(SeatHolding.speaker_id))
            .order_by(col(SeatHolding.id))
        )
        return [SeatHoldingCheckRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_ids(self, seat_holding_ids: list[int]) -> int:
        statement = delete(SeatHolding).where(col(SeatHolding.id).in_(seat_holding_ids))

        return self.session.exec(statement).rowcount

    def get_first_sitting_date_decade_counts(self) -> list[SeatHoldingDecadeCount]:
        decade = (
            func.floor(
                func.extract("year", col(SeatHolding.first_sitting_date))
                / _YEARS_IN_DECADE
            )
            * _YEARS_IN_DECADE
        ).cast(Integer)
        statement = select(decade, func.count()).group_by(decade)
        return [
            SeatHoldingDecadeCount(*row) for row in self.session.exec(statement).all()
        ]

    def get_count_by_division_key_not_equal_folded_location_name(
        self, separator_pattern: str, suffix_pattern: str
    ) -> int:
        folded_location_name = func.lower(
            func.regexp_replace(
                func.btrim(
                    func.regexp_replace(
                        SeatHolding.location_name,
                        separator_pattern,
                        " ",
                        _REPLACE_ALL,
                    )
                ),
                suffix_pattern,
                "",
                _CASE_INSENSITIVE,
            )
        )
        statement = (
            select(func.count())
            .select_from(SeatHolding)
            .where(col(SeatHolding.division_key) != folded_location_name)
        )
        return self.session.exec(statement).one()
