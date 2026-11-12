from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session, col, delete, select

from database.division_party_count import DivisionPartyCount
from enums import DivisionVoteChoice, DivisionVoteListSource


@dataclass(frozen=True)
class DivisionPartyCountRow:
    division_id: int
    list_source: DivisionVoteListSource
    vote_choice: DivisionVoteChoice
    party: Optional[str]
    member_count: int
    uncertain_member_count: int


class CRUDDivisionPartyCount:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, division_party_counts: list[DivisionPartyCount]) -> None:
        self.session.add_all(division_party_counts)
        self.session.flush()

    def get_rows_by_division_ids(
        self, division_ids: list[int]
    ) -> list[DivisionPartyCountRow]:
        statement = (
            select(
                DivisionPartyCount.division_id,
                DivisionPartyCount.list_source,
                DivisionPartyCount.vote_choice,
                DivisionPartyCount.party,
                DivisionPartyCount.member_count,
                DivisionPartyCount.uncertain_member_count,
            )
            .where(col(DivisionPartyCount.division_id).in_(division_ids))
            .order_by(DivisionPartyCount.division_id, DivisionPartyCount.id)
        )
        return [
            DivisionPartyCountRow(*row) for row in self.session.exec(statement).all()
        ]

    def get_distinct_division_ids(self) -> list[int]:
        statement = (
            select(DivisionPartyCount.division_id)
            .distinct()
            .order_by(DivisionPartyCount.division_id)
        )
        return list(self.session.exec(statement).all())

    def delete_by_division_ids(self, division_ids: list[int]) -> int:
        statement = delete(DivisionPartyCount).where(
            col(DivisionPartyCount.division_id).in_(division_ids)
        )

        return self.session.exec(statement).rowcount
