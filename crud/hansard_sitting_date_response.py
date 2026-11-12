from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlmodel import Session, col, select

from database.hansard_sitting_date_response import HansardSittingDateResponse

_LIST_COLUMNS = ("sections", "annexures", "vernaculars", "a2b")
_LIST_FILLABLE = "(raw.{column} IS NULL AND sitting.{column} IS NOT NULL)"
_ANY_LIST_FILLABLE = " OR ".join(
    _LIST_FILLABLE.format(column=column) for column in _LIST_COLUMNS
)


@dataclass(frozen=True)
class SittingListFillCounts:
    rows: int
    sections: int
    annexures: int
    vernaculars: int
    a2b: int


class CRUDHansardSittingDateResponse:
    def __init__(self, session: Session):
        self.session = session

    def lock_table_in_share_row_exclusive_mode(self) -> None:
        statement = text(
            "LOCK TABLE hansardsittingdateresponse IN SHARE ROW EXCLUSIVE MODE"
        )

        self.session.execute(statement)

    def create(self, hansard_sitting_date_response: HansardSittingDateResponse) -> None:
        self.session.add(hansard_sitting_date_response)
        self.session.commit()

    def add_many(
        self, hansard_sitting_date_responses: list[HansardSittingDateResponse]
    ) -> None:
        self.session.add_all(hansard_sitting_date_responses)
        self.session.flush()

    def update(self, hansard_sitting_date_response: HansardSittingDateResponse) -> None:
        self.session.add(hansard_sitting_date_response)
        self.session.flush()

    def get_all(self) -> list[HansardSittingDateResponse]:
        statement = select(HansardSittingDateResponse)
        return list(self.session.exec(statement).all())

    def get_sitting_dates_by_sitting_date_not_null(self) -> set[str]:
        statement = select(HansardSittingDateResponse.sitting_date).where(
            col(HansardSittingDateResponse.sitting_date).is_not(None)
        )
        return set(self.session.exec(statement).all())

    def get_by_sitting_date(
        self, sitting_date: str
    ) -> Optional[HansardSittingDateResponse]:
        statement = select(HansardSittingDateResponse).where(
            HansardSittingDateResponse.sitting_date == sitting_date
        )
        return self.session.exec(statement).first()

    def get_fill_counts_by_sitting_sitting_date_and_lists_null(
        self,
    ) -> SittingListFillCounts:
        statement = text(
            f"SELECT count(*) FILTER (WHERE {_ANY_LIST_FILLABLE}), "
            + ", ".join(
                f"count(*) FILTER (WHERE {_LIST_FILLABLE.format(column=column)})"
                for column in _LIST_COLUMNS
            )
            + " FROM hansardsittingdateresponse AS raw "
            "JOIN sitting ON sitting.sitting_date = raw.sitting_date"
        )

        return SittingListFillCounts(*self.session.execute(statement).one())

    def set_sections_annexures_vernaculars_and_a2b_from_sitting_by_sitting_date(
        self,
    ) -> int:
        # NOTE: a column the raw row already holds is kept, and a column the sitting lacks leaves the raw column as it is.
        statement = text(
            "UPDATE hansardsittingdateresponse AS raw SET "
            + ", ".join(
                f"{column} = COALESCE(raw.{column}, sitting.{column})"
                for column in _LIST_COLUMNS
            )
            + " FROM sitting "
            f"WHERE sitting.sitting_date = raw.sitting_date AND ({_ANY_LIST_FILLABLE})"
        )

        return self.session.connection().execute(statement).rowcount
