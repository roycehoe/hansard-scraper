from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session, col, delete, select

from database.division_vote import DivisionVote
from enums import DivisionVoteChoice, DivisionVoteListSource, DivisionVoteNameRule


@dataclass(frozen=True)
class DivisionVoteRow:
    division_id: int
    list_source: DivisionVoteListSource
    ordinal: int
    printed_name: str
    vote_choice: DivisionVoteChoice
    speaker_id: Optional[int]
    name_rule: Optional[DivisionVoteNameRule]
    party: Optional[str]
    is_party_uncertain: bool


class CRUDDivisionVote:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, division_votes: list[DivisionVote]) -> None:
        self.session.add_all(division_votes)
        self.session.flush()

    def get_rows_by_division_ids_and_list_source(
        self, division_ids: list[int], list_source: DivisionVoteListSource
    ) -> list[DivisionVoteRow]:
        statement = (
            select(
                DivisionVote.division_id,
                DivisionVote.list_source,
                DivisionVote.ordinal,
                DivisionVote.printed_name,
                DivisionVote.vote_choice,
                DivisionVote.speaker_id,
                DivisionVote.name_rule,
                DivisionVote.party,
                DivisionVote.is_party_uncertain,
            )
            .where(col(DivisionVote.division_id).in_(division_ids))
            .where(col(DivisionVote.list_source) == list_source)
            .order_by(DivisionVote.division_id, DivisionVote.ordinal)
        )
        return [DivisionVoteRow(*row) for row in self.session.exec(statement).all()]

    def get_distinct_division_ids(self) -> list[int]:
        statement = select(DivisionVote.division_id).distinct().order_by(
            DivisionVote.division_id
        )
        return list(self.session.exec(statement).all())

    def delete_by_division_ids_and_list_source(
        self, division_ids: list[int], list_source: DivisionVoteListSource
    ) -> int:
        statement = (
            delete(DivisionVote)
            .where(col(DivisionVote.division_id).in_(division_ids))
            .where(col(DivisionVote.list_source) == list_source)
        )

        return self.session.exec(statement).rowcount

    def delete_by_division_ids(self, division_ids: list[int]) -> int:
        statement = delete(DivisionVote).where(
            col(DivisionVote.division_id).in_(division_ids)
        )

        return self.session.exec(statement).rowcount
