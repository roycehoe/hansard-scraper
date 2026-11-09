from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from database.division import Division
from database.division_vote import DivisionVote
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from enums import (
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
    MinutesDivisionPairing,
    MinutesStatus,
)

_SITTING_DATE = date(2021, 10, 4)
_ORDINAL = 1


def _add_minutes_and_division(session: Session) -> tuple[Minutes, Division]:
    minutes = Minutes(sitting_date=_SITTING_DATE, status=MinutesStatus.LISTED)
    division = Division(
        sitting_date=_SITTING_DATE,
        parliament_number=14,
        count_source=DivisionCountSource.PRINTED_LINE,
        printed_counts="Ayes 75, Noes 11",
        list_status=DivisionListStatus.NOT_PRINTED,
    )
    session.add(minutes)
    session.add(division)
    session.flush()
    return minutes, division


def _build_minutes_division(minutes_id: int, division_id: int) -> MinutesDivision:
    return MinutesDivision(
        ordinal=_ORDINAL,
        printed_counts="Ayes 75, Noes 11",
        ayes=75,
        noes=11,
        list_status=DivisionListStatus.NOT_PRINTED,
        pairing=MinutesDivisionPairing.PAIRED,
        minutes_id=minutes_id,
        division_id=division_id,
    )


def _build_division_vote(
    division_id: int, list_source: DivisionVoteListSource
) -> DivisionVote:
    return DivisionVote(
        ordinal=_ORDINAL,
        printed_name="Abdul Samad",
        vote_choice=DivisionVoteChoice.AYE,
        list_source=list_source,
        division_id=division_id,
    )


def test_minutes_division_refuses_a_second_row_for_one_ordinal(
    scratch_session: Session,
) -> None:
    minutes, division = _add_minutes_and_division(scratch_session)
    assert minutes.id is not None
    assert division.id is not None
    scratch_session.add(_build_minutes_division(minutes.id, division.id))
    scratch_session.add(_build_minutes_division(minutes.id, division.id))

    with pytest.raises(IntegrityError):
        scratch_session.flush()


def test_division_vote_refuses_a_second_row_for_one_list_source_and_ordinal(
    scratch_session: Session,
) -> None:
    _, division = _add_minutes_and_division(scratch_session)
    assert division.id is not None
    scratch_session.add(
        _build_division_vote(division.id, DivisionVoteListSource.MINUTES)
    )
    scratch_session.add(
        _build_division_vote(division.id, DivisionVoteListSource.MINUTES)
    )

    with pytest.raises(IntegrityError):
        scratch_session.flush()


def test_division_vote_allows_the_same_ordinal_in_the_two_lists(
    scratch_session: Session,
) -> None:
    _, division = _add_minutes_and_division(scratch_session)
    assert division.id is not None
    scratch_session.add(
        _build_division_vote(division.id, DivisionVoteListSource.MINUTES)
    )
    scratch_session.add(
        _build_division_vote(division.id, DivisionVoteListSource.HANSARD)
    )

    scratch_session.flush()
