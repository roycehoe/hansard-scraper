from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import populate.speakers as populate_speakers_module
import scripts.load_colonial_la_speakers as load_colonial_la_speakers_script
import scripts.load_heads_of_state as load_heads_of_state_script
import scripts.scrape_speakers_by_parliament as scrape_speakers_by_parliament_script
from crud.speaker import CRUDSpeaker
from database.speaker import Speaker
from enums import LegislativeAssemblyFlag
from exceptions import HansardWriteTargetError
from populate.speakers import populate_speakers
from schemas.parliament_member_list_response import (
    ParliamentMember,
    ParliamentMemberListResponse,
    ParliamentMembers,
    ParliamentMemberSession,
    ParliamentMembersMeta,
    ParliamentOption,
)
from utils.data_files import (
    get_colonial_members,
    get_heads_of_state,
    get_unscraped_members,
)

_SCRAPED_NAMES = ("Pritam Singh", "New Member")
_PARTY = "WP"
_SESSION_ID = "session-15"
_PARLIAMENT_TITLE = "15th Parliament"
_REFUSAL_MESSAGE = "Refusing to write: test target"


@dataclass
class _CommitRecorder:
    original_commit: Callable[[], None]
    commit_count: int = 0

    def commit(self) -> None:
        self.commit_count += 1
        self.original_commit()


def _record_commits(session: Session, monkeypatch: pytest.MonkeyPatch) -> _CommitRecorder:
    recorder = _CommitRecorder(session.commit)
    monkeypatch.setattr(session, "commit", recorder.commit)
    return recorder


def _get_member(name: str) -> ParliamentMember:
    return ParliamentMember(
        full_name=name,
        party_affliation=_PARTY,
        legislative_assembly=LegislativeAssemblyFlag.NO,
        parliament_session=[ParliamentMemberSession(parliament_sessions_id=_SESSION_ID)],
    )


def _get_parliament_member_list_response() -> ParliamentMemberListResponse:
    return ParliamentMemberListResponse(
        mps=ParliamentMembers(
            meta=ParliamentMembersMeta(filter_count=len(_SCRAPED_NAMES)), data=[_get_member(name) for name in _SCRAPED_NAMES]
        ),
        options=[ParliamentOption(title=_PARLIAMENT_TITLE, parliament_sessions=[_SESSION_ID])],
    )


def _refuse_write_target(database_url: str) -> None:
    raise HansardWriteTargetError(_REFUSAL_MESSAGE)


def _get_colonial_member_count() -> int:
    return len({(member.name, member.parliament_number) for member in get_colonial_members() + get_unscraped_members()})


def _seed_head_of_state_member(session: Session) -> Speaker:
    head_of_state = get_heads_of_state()[0]
    speaker = Speaker(name=head_of_state.name, party=_PARTY, is_legislative_assembly=False, parliament_number=head_of_state.parliament_number)
    session.add(speaker)
    session.commit()
    return speaker


def test_colonial_dry_run_inserts_nothing(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _record_commits(scratch_session, monkeypatch)

    load_colonial_la_speakers_script.store_colonial_speakers(scratch_session, is_commit=False)

    scratch_session.rollback()
    assert CRUDSpeaker(scratch_session).get_all() == []
    assert recorder.commit_count == 0


def test_colonial_commit_inserts_each_member_once_in_one_commit(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _record_commits(scratch_session, monkeypatch)

    load_colonial_la_speakers_script.store_colonial_speakers(scratch_session, is_commit=True)

    scratch_session.rollback()
    assert len(CRUDSpeaker(scratch_session).get_all()) == _get_colonial_member_count()
    assert recorder.commit_count == 1


def test_colonial_second_commit_inserts_nothing(scratch_session: Session) -> None:
    load_colonial_la_speakers_script.store_colonial_speakers(scratch_session, is_commit=True)
    load_colonial_la_speakers_script.store_colonial_speakers(scratch_session, is_commit=True)

    scratch_session.rollback()
    assert len(CRUDSpeaker(scratch_session).get_all()) == _get_colonial_member_count()


def test_heads_of_state_dry_run_inserts_and_marks_nothing(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seeded_speaker = _seed_head_of_state_member(scratch_session)
    recorder = _record_commits(scratch_session, monkeypatch)

    load_heads_of_state_script.store_heads_of_state(scratch_session, is_commit=False)

    scratch_session.rollback()
    assert CRUDSpeaker(scratch_session).get_all() == [seeded_speaker]
    assert seeded_speaker.is_member
    assert recorder.commit_count == 0


def test_heads_of_state_commit_inserts_the_missing_rows_and_marks_the_stored_member(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded_speaker = _seed_head_of_state_member(scratch_session)
    recorder = _record_commits(scratch_session, monkeypatch)

    load_heads_of_state_script.store_heads_of_state(scratch_session, is_commit=True)

    scratch_session.rollback()
    speakers = CRUDSpeaker(scratch_session).get_all()
    assert len(speakers) == len(get_heads_of_state())
    assert all(not speaker.is_member for speaker in speakers)
    assert seeded_speaker.party == _PARTY
    assert recorder.commit_count == 1


def test_scrape_dry_run_inserts_nothing(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(populate_speakers_module, "get_parliament_member_list_response", _get_parliament_member_list_response)
    recorder = _record_commits(scratch_session, monkeypatch)

    populate_speakers(scratch_session, is_commit=False)

    scratch_session.rollback()
    assert CRUDSpeaker(scratch_session).get_all() == []
    assert recorder.commit_count == 0


def test_scrape_commit_inserts_every_member_in_one_commit(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(populate_speakers_module, "get_parliament_member_list_response", _get_parliament_member_list_response)
    recorder = _record_commits(scratch_session, monkeypatch)

    populate_speakers(scratch_session, is_commit=True)

    scratch_session.rollback()
    assert sorted(speaker.name for speaker in CRUDSpeaker(scratch_session).get_all()) == sorted(_SCRAPED_NAMES)
    assert recorder.commit_count == 1


@pytest.mark.parametrize(
    ("script_module", "load_speakers"),
    [
        (load_colonial_la_speakers_script, load_colonial_la_speakers_script.load_colonial_la_speakers),
        (load_heads_of_state_script, load_heads_of_state_script.load_heads_of_state),
        (scrape_speakers_by_parliament_script, scrape_speakers_by_parliament_script.scrape_speakers_by_parliament),
    ],
)
def test_refused_write_target_raises_before_any_row_is_written(
    script_module: ModuleType,
    load_speakers: Callable[[bool], None],
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(script_module, "validate_can_write", _refuse_write_target)
    monkeypatch.setattr(script_module, "engine", scratch_engine)
    monkeypatch.setattr(populate_speakers_module, "get_parliament_member_list_response", _get_parliament_member_list_response)

    with pytest.raises(HansardWriteTargetError, match=_REFUSAL_MESSAGE):
        load_speakers(True)

    assert CRUDSpeaker(scratch_session).get_all() == []
