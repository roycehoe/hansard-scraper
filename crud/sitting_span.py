from dataclasses import dataclass

from sqlalchemy import Integer, text, update
from sqlmodel import Session, col, delete, func, select

from database.sitting_span import SittingSpan
from utils.sitting_span_update import SittingSpanUpdate

_YEARS_IN_DECADE = 10


@dataclass(frozen=True)
class SittingSpanDecadeCount:
    decade: int
    sitting_span_count: int


class CRUDSittingSpan:
    def __init__(self, session: Session):
        self.session = session

    def lock_table_in_share_row_exclusive_mode(self) -> None:
        statement = text("LOCK TABLE sitting_span IN SHARE ROW EXCLUSIVE MODE")

        self.session.execute(statement)

    def add_many(self, sitting_spans: list[SittingSpan]) -> None:
        self.session.add_all(sitting_spans)
        self.session.flush()

    def get_by_speaker_ids(self, speaker_ids: list[int]) -> list[SittingSpan]:
        statement = select(SittingSpan).where(
            col(SittingSpan.speaker_id).in_(speaker_ids)
        )
        return list(self.session.exec(statement).all())

    def get_distinct_speaker_ids(self) -> list[int]:
        statement = select(SittingSpan.speaker_id).distinct()
        return list(self.session.exec(statement).all())

    def update_many(self, sitting_span_updates: list[SittingSpanUpdate]) -> None:
        if not sitting_span_updates:
            return

        self.session.execute(
            update(SittingSpan),
            [
                {
                    "id": sitting_span_update.id,
                    "first_sitting_date": sitting_span_update.first_sitting_date,
                    "last_sitting_date": sitting_span_update.last_sitting_date,
                    "sitting_count": sitting_span_update.sitting_count,
                }
                for sitting_span_update in sitting_span_updates
            ],
        )
        self.session.flush()

    def delete_by_ids(self, sitting_span_ids: list[int]) -> int:
        statement = delete(SittingSpan).where(col(SittingSpan.id).in_(sitting_span_ids))

        return self.session.exec(statement).rowcount

    def get_first_sitting_date_decade_counts(self) -> list[SittingSpanDecadeCount]:
        decade = (
            func.floor(
                func.extract("year", col(SittingSpan.first_sitting_date))
                / _YEARS_IN_DECADE
            )
            * _YEARS_IN_DECADE
        ).cast(Integer)
        statement = select(decade, func.count()).group_by(decade)
        return [
            SittingSpanDecadeCount(*row) for row in self.session.exec(statement).all()
        ]
