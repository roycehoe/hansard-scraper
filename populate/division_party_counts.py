from collections import Counter, defaultdict
from typing import Iterable, Union

from sqlmodel import Session

from crud.division import CRUDDivision
from crud.division_party_count import CRUDDivisionPartyCount, DivisionPartyCountRow
from crud.division_vote import CRUDDivisionVote, DivisionVoteRow
from crud.minutes_division import CRUDMinutesDivision
from database.division_party_count import DivisionPartyCount
from enums import DivisionListStatus, DivisionVoteListSource
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.division_party_count_plan import (
    DivisionPartyCountPlan,
    PlannedDivisionPartyCount,
)
from services.division_party_count import (
    DivisionVoteInput,
    get_division_party_counts,
)

_DIVISION_BATCH = 200


def _build_vote_inputs(vote_rows: list[DivisionVoteRow]) -> list[DivisionVoteInput]:
    return [
        DivisionVoteInput(
            vote_choice=vote_row.vote_choice,
            party=vote_row.party,
            is_party_uncertain=vote_row.is_party_uncertain,
        )
        for vote_row in vote_rows
    ]


def _get_batch_plan(
    session: Session, batch_division_ids: list[int]
) -> DivisionPartyCountPlan:
    divisions = CRUDDivision(session).get_by_ids(batch_division_ids)
    division_id_to_minutes_list_status: dict[int, DivisionListStatus] = {}
    for minutes_division_row in CRUDMinutesDivision(session).get_rows_by_division_ids(
        batch_division_ids
    ):
        if (
            division_id_to_minutes_list_status.get(minutes_division_row.division_id)
            is not None
        ):
            raise HansardWriteCheckError(
                f"Division {minutes_division_row.division_id} has two minutes divisions"
            )
        division_id_to_minutes_list_status[minutes_division_row.division_id] = (
            minutes_division_row.list_status
        )
    division_id_to_minutes_votes: defaultdict[int, list[DivisionVoteRow]] = (
        defaultdict(list)
    )
    division_id_to_hansard_votes: defaultdict[int, list[DivisionVoteRow]] = (
        defaultdict(list)
    )
    for list_source, division_id_to_votes in (
        (DivisionVoteListSource.MINUTES, division_id_to_minutes_votes),
        (DivisionVoteListSource.HANSARD, division_id_to_hansard_votes),
    ):
        for vote_row in CRUDDivisionVote(
            session
        ).get_rows_by_division_ids_and_list_source(batch_division_ids, list_source):
            division_id_to_votes[vote_row.division_id].append(vote_row)
    division_ids: list[int] = []
    planned_party_counts: list[PlannedDivisionPartyCount] = []
    for division in divisions:
        if division.id is None:
            raise HansardWriteCheckError("A stored division holds no id")
        division_ids.append(division.id)
        planned_party_counts.extend(
            PlannedDivisionPartyCount(
                division_id=division.id,
                list_source=party_count.list_source,
                vote_choice=party_count.vote_choice,
                party=party_count.party,
                member_count=party_count.member_count,
                uncertain_member_count=party_count.uncertain_member_count,
            )
            for party_count in get_division_party_counts(
                _build_vote_inputs(division_id_to_minutes_votes[division.id]),
                _build_vote_inputs(division_id_to_hansard_votes[division.id]),
                division_id_to_minutes_list_status.get(division.id)
                == DivisionListStatus.STORED,
                division.list_status == DivisionListStatus.STORED,
            )
        )
    return DivisionPartyCountPlan(
        division_ids=division_ids, party_counts=planned_party_counts
    )


def get_division_party_count_plan(
    session: Session, division_ids: list[int]
) -> DivisionPartyCountPlan:
    planned_division_ids: list[int] = []
    planned_party_counts: list[PlannedDivisionPartyCount] = []
    sorted_division_ids = sorted(division_ids)
    for start in range(0, len(sorted_division_ids), _DIVISION_BATCH):
        batch_plan = _get_batch_plan(
            session, sorted_division_ids[start : start + _DIVISION_BATCH]
        )
        planned_division_ids.extend(batch_plan.division_ids)
        planned_party_counts.extend(batch_plan.party_counts)
    return DivisionPartyCountPlan(
        division_ids=planned_division_ids, party_counts=planned_party_counts
    )


def _get_member_counts(
    party_counts: Iterable[Union[DivisionPartyCountRow, PlannedDivisionPartyCount]],
) -> Counter:
    member_counts: Counter = Counter()
    for party_count in party_counts:
        member_counts[
            (
                party_count.list_source,
                party_count.vote_choice,
                party_count.party is not None,
            )
        ] += party_count.member_count
    return member_counts


def _validate_can_commit_division_party_counts(
    session: Session, plan: DivisionPartyCountPlan
) -> None:
    stored_rows = CRUDDivisionPartyCount(session).get_rows_by_division_ids(
        plan.division_ids
    )
    if len(stored_rows) != len(plan.party_counts):
        raise HansardWriteCheckError(
            f"{len(stored_rows)} stored party count rows, planned {len(plan.party_counts)}"
        )
    stored_member_counts = _get_member_counts(stored_rows)
    planned_member_counts = _get_member_counts(plan.party_counts)
    if stored_member_counts != planned_member_counts:
        raise HansardWriteCheckError(
            f"The stored party counts by source, choice and link {dict(stored_member_counts)} differ from the plan {dict(planned_member_counts)}"
        )


def _insert_party_counts(session: Session, plan: DivisionPartyCountPlan) -> None:
    CRUDDivisionPartyCount(session).add_many(
        [
            DivisionPartyCount(
                member_count=planned.member_count,
                uncertain_member_count=planned.uncertain_member_count,
                party=planned.party,
                list_source=planned.list_source,
                vote_choice=planned.vote_choice,
                division_id=planned.division_id,
            )
            for planned in plan.party_counts
        ]
    )
    _validate_can_commit_division_party_counts(session, plan)


def write_division_party_count_plan(
    session: Session, plan: DivisionPartyCountPlan
) -> None:
    for start in range(0, len(plan.division_ids), _DIVISION_BATCH):
        batch_division_ids = plan.division_ids[start : start + _DIVISION_BATCH]
        stored_count = len(
            CRUDDivisionPartyCount(session).get_rows_by_division_ids(batch_division_ids)
        )
        deleted_count = CRUDDivisionPartyCount(session).delete_by_division_ids(
            batch_division_ids
        )
        if deleted_count != stored_count:
            raise HansardWriteCheckError(
                f"Deleted {deleted_count} party count rows, read {stored_count}"
            )
    _insert_party_counts(session, plan)


# NOTE: inserts only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_division_party_counts(session: Session, division_ids: list[int]) -> None:
    division_ids_with_rows = {
        stored_row.division_id
        for stored_row in CRUDDivisionPartyCount(session).get_rows_by_division_ids(
            division_ids
        )
    }
    plan = get_division_party_count_plan(
        session,
        [
            division_id
            for division_id in division_ids
            if division_id not in division_ids_with_rows
        ],
    )
    _insert_party_counts(session, plan)
    logger.info(
        f"Division party counts: added {len(plan.party_counts)} rows for {len(plan.division_ids)} divisions"
    )
