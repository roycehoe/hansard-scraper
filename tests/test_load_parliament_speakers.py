import pytest
from sqlmodel import Session

import scripts.load_parliament_speakers as load_parliament_speakers_script
from crud.speaker import CRUDSpeaker
from database.speaker import Speaker
from schemas.speaker import SpeakerResult

_PARLIAMENT_NUMBER = 15
_STORED_NAME = "Pritam Singh"
_NEW_NAME = "New Member"
_PARTY = "WP"
_EXPECTED_ROW_COUNT_AFTER_COMMIT = 2


def _get_speaker_results(parliament_number: int) -> list[SpeakerResult]:
    return [
        SpeakerResult(name=_STORED_NAME, party=_PARTY, is_legislative_assembly=False, parliament_number=parliament_number),
        SpeakerResult(name=_NEW_NAME, party=_PARTY, is_legislative_assembly=False, parliament_number=parliament_number),
    ]


@pytest.fixture
def seeded_session(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    monkeypatch.setattr(load_parliament_speakers_script, "get_speakers_by_parliament_number", _get_speaker_results)
    scratch_session.add(
        Speaker(name=_STORED_NAME, party=_PARTY, is_legislative_assembly=False, parliament_number=_PARLIAMENT_NUMBER)
    )
    scratch_session.commit()
    return scratch_session


def test_dry_run_inserts_nothing(seeded_session: Session) -> None:
    load_parliament_speakers_script.load_parliament_speakers(seeded_session, _PARLIAMENT_NUMBER, is_commit=False)

    seeded_session.rollback()
    assert [speaker.name for speaker in CRUDSpeaker(seeded_session).get_all()] == [_STORED_NAME]


def test_commit_inserts_only_the_unstored_member(seeded_session: Session) -> None:
    load_parliament_speakers_script.load_parliament_speakers(seeded_session, _PARLIAMENT_NUMBER, is_commit=True)

    seeded_session.rollback()
    speakers = CRUDSpeaker(seeded_session).get_all()
    assert len(speakers) == _EXPECTED_ROW_COUNT_AFTER_COMMIT
    assert sorted(speaker.name for speaker in speakers) == [_NEW_NAME, _STORED_NAME]
    assert all(speaker.parliament_number == _PARLIAMENT_NUMBER for speaker in speakers)
