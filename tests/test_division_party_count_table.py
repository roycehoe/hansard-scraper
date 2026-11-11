from datetime import date
from typing import Optional

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from database.division import Division
from database.division_party_count import DivisionPartyCount
from enums import (
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
)

_SITTING_DATE = date(2021, 10, 4)
_PARTY = "PAP"


def _add_division(session: Session) -> Division:
    division = Division(
        sitting_date=_SITTING_DATE,
        parliament_number=14,
        count_source=DivisionCountSource.PRINTED_LINE,
        printed_counts="Ayes 75, Noes 11",
        list_status=DivisionListStatus.NOT_PRINTED,
    )
    session.add(division)
    session.flush()
    return division


def _build_party_count(
    division_id: int, vote_choice: DivisionVoteChoice, party: Optional[str]
) -> DivisionPartyCount:
    return DivisionPartyCount(
        member_count=3,
        uncertain_member_count=0,
        party=party,
        list_source=DivisionVoteListSource.MINUTES,
        vote_choice=vote_choice,
        division_id=division_id,
    )


def test_two_rows_with_a_null_party_for_one_division_and_choice_are_refused(
    scratch_session: Session,
) -> None:
    division = _add_division(scratch_session)
    assert division.id is not None
    scratch_session.add(_build_party_count(division.id, DivisionVoteChoice.AYE, None))
    scratch_session.add(_build_party_count(division.id, DivisionVoteChoice.AYE, None))

    with pytest.raises(IntegrityError):
        scratch_session.flush()


def test_two_rows_for_one_party_in_different_choices_are_allowed(
    scratch_session: Session,
) -> None:
    division = _add_division(scratch_session)
    assert division.id is not None
    scratch_session.add(_build_party_count(division.id, DivisionVoteChoice.AYE, _PARTY))
    scratch_session.add(_build_party_count(division.id, DivisionVoteChoice.NO, _PARTY))

    scratch_session.flush()


def test_an_absent_choice_is_refused_by_the_check_constraint(
    scratch_session: Session,
) -> None:
    division = _add_division(scratch_session)
    assert division.id is not None
    scratch_session.add(
        _build_party_count(division.id, DivisionVoteChoice.ABSENT, _PARTY)
    )

    with pytest.raises(IntegrityError):
        scratch_session.flush()
