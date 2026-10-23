import pytest
from sqlmodel import Session

import scripts.load_parliament_speakers as load_parliament_speakers_script
from crud.speaker import CRUDSpeaker
from database.speaker import Speaker
from enums import LegislativeAssemblyFlag
from exceptions import HansardMemberListError
from schemas.parliament_member_list_response import (
    ParliamentMember,
    ParliamentMemberListResponse,
    ParliamentMembers,
    ParliamentMemberSession,
    ParliamentMembersMeta,
    ParliamentOption,
)

_PARLIAMENT_NUMBER = 15
_STORED_NAME = "Pritam Singh"
_NEW_NAME = "New Member"
_PARTY = "WP"
_EXPECTED_ROW_COUNT_AFTER_COMMIT = 2
_SESSION_ID = "session-15"
_PARLIAMENT_TITLE = "15th Parliament"
_UNKNOWN_PARLIAMENT_NUMBER = 99


def _get_member(name: str) -> ParliamentMember:
    return ParliamentMember(
        full_name=name,
        party_affliation=_PARTY,
        legislative_assembly=LegislativeAssemblyFlag.NO,
        parliament_session=[ParliamentMemberSession(parliament_sessions_id=_SESSION_ID)],
    )


def _get_parliament_member_list_response() -> ParliamentMemberListResponse:
    return ParliamentMemberListResponse(
        mps=ParliamentMembers(meta=ParliamentMembersMeta(filter_count=2), data=[_get_member(_STORED_NAME), _get_member(_NEW_NAME)]),
        options=[ParliamentOption(title=_PARLIAMENT_TITLE, parliament_sessions=[_SESSION_ID])],
    )


@pytest.fixture
def seeded_session(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    monkeypatch.setattr(load_parliament_speakers_script, "get_parliament_member_list_response", _get_parliament_member_list_response)
    scratch_session.add(
        Speaker(name=_STORED_NAME, party=_PARTY, is_legislative_assembly=False, parliament_number=_PARLIAMENT_NUMBER)
    )
    scratch_session.commit()
    return scratch_session


def test_dry_run_inserts_nothing(seeded_session: Session) -> None:
    load_parliament_speakers_script.store_new_speakers(seeded_session, _PARLIAMENT_NUMBER, is_commit=False)

    seeded_session.rollback()
    assert [speaker.name for speaker in CRUDSpeaker(seeded_session).get_all()] == [_STORED_NAME]


def test_commit_inserts_only_the_unstored_member(seeded_session: Session) -> None:
    load_parliament_speakers_script.store_new_speakers(seeded_session, _PARLIAMENT_NUMBER, is_commit=True)

    seeded_session.rollback()
    speakers = CRUDSpeaker(seeded_session).get_all()
    assert len(speakers) == _EXPECTED_ROW_COUNT_AFTER_COMMIT
    assert sorted(speaker.name for speaker in speakers) == [_NEW_NAME, _STORED_NAME]
    assert all(speaker.parliament_number == _PARLIAMENT_NUMBER for speaker in speakers)


def test_unknown_parliament_raises(seeded_session: Session) -> None:
    with pytest.raises(HansardMemberListError, match=f"No member list for parliament {_UNKNOWN_PARLIAMENT_NUMBER}"):
        load_parliament_speakers_script.store_new_speakers(seeded_session, _UNKNOWN_PARLIAMENT_NUMBER, is_commit=False)
