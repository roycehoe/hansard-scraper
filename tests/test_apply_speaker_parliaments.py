import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_speaker_parliaments as apply_speaker_parliaments_script
from database.speaker import Speaker
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.hand_kept_member import HandKeptMember

_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_COLONIAL_MEMBERS = [HandKeptMember(name="Ann Lee", party="Labour Front", is_legislative_assembly=True, parliament_number=0, comments=None)]


def _build_speaker(name: str, parliament_number: int) -> Speaker:
    return Speaker(name=name, party="Labour Front", is_legislative_assembly=True, parliament_number=parliament_number)


def _seed_speakers(scratch_session: Session) -> list[Speaker]:
    speakers = [_build_speaker("Ann Lee", 1), _build_speaker("Cara Lim", 1)]
    scratch_session.add_all(speakers)
    scratch_session.commit()
    return speakers


def _get_stored_parliaments(scratch_session: Session, seeded: list[Speaker]) -> list[int]:
    scratch_session.expire_all()
    return [scratch_session.get_one(Speaker, speaker.id).parliament_number for speaker in seeded]


@pytest.fixture(autouse=True)
def _use_scratch_data(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apply_speaker_parliaments_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_speaker_parliaments_script, "get_colonial_members", lambda: _COLONIAL_MEMBERS)
    monkeypatch.setattr(apply_speaker_parliaments_script, "get_heads_of_state", lambda: [])


def test_dry_run_writes_the_plan_and_changes_no_row(scratch_session: Session, tmp_path: Path) -> None:
    seeded = _seed_speakers(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_speaker_parliaments_script.apply_speaker_parliaments(is_commit=False, plan_path=plan_path)

    assert json.loads(plan_path.read_text()) == [
        {"id": seeded[0].id, "name": "Ann Lee", "parliament_number_before": 1, "parliament_number_after": 0}
    ]
    assert _get_stored_parliaments(scratch_session, seeded) == [1, 1]


def test_commit_refuses_after_a_row_appears_in_both_parliaments(scratch_session: Session) -> None:
    seeded = _seed_speakers(scratch_session)
    assembly_speaker = _build_speaker("Ann Lee", 0)
    scratch_session.add(assembly_speaker)
    scratch_session.commit()

    with pytest.raises(HansardWriteCheckError, match="exist in Parliament 0 and 1"):
        apply_speaker_parliaments_script.apply_speaker_parliaments(is_commit=True, plan_path=None)

    assert _get_stored_parliaments(scratch_session, seeded) == [1, 1]


def test_commit_on_an_unchanged_state_writes_exactly_the_plan(scratch_session: Session) -> None:
    seeded = _seed_speakers(scratch_session)

    apply_speaker_parliaments_script.apply_speaker_parliaments(is_commit=True, plan_path=None)

    assert _get_stored_parliaments(scratch_session, seeded) == [0, 1]

    apply_speaker_parliaments_script.apply_speaker_parliaments(is_commit=True, plan_path=None)

    assert _get_stored_parliaments(scratch_session, seeded) == [0, 1]


def test_commit_refuses_the_protected_local_port_and_writes_nothing(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seeded = _seed_speakers(scratch_session)
    monkeypatch.setattr(apply_speaker_parliaments_script, "settings", SimpleNamespace(database_url=_PROTECTED_DATABASE_URL))

    with pytest.raises(HansardWriteTargetError, match="5432"):
        apply_speaker_parliaments_script.apply_speaker_parliaments(is_commit=True, plan_path=None)

    assert _get_stored_parliaments(scratch_session, seeded) == [1, 1]
