import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_speaker_overrides as apply_speaker_overrides_script
from database.speaker import Speaker
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.speaker_override import (
    LegislativeAssemblyOverride,
    PartyOverride,
    SpeakerOverrides,
)

_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_OLD_PARTY = "Labour Front"
_NEW_PARTY = "Workers' Party"
_UNRELATED_PARTY = "People's Action Party"
_OVERRIDES = SpeakerOverrides(
    legislative_assembly_overrides=[
        LegislativeAssemblyOverride(
            name="Ann Lee", parliament_number=1, source_is_legislative_assembly=False, is_legislative_assembly=True, reason="test"
        )
    ],
    party_overrides=[PartyOverride(name="Bob Tan", parliament_number=2, source_party=_OLD_PARTY, party=_NEW_PARTY, reason="test")],
)


def _build_speaker(name: str, parliament_number: int, party: str, is_legislative_assembly: bool) -> Speaker:
    return Speaker(name=name, party=party, is_legislative_assembly=is_legislative_assembly, parliament_number=parliament_number)


def _seed_speakers(scratch_session: Session, bob_party: str = _OLD_PARTY) -> list[Speaker]:
    speakers = [
        _build_speaker("Ann Lee", 1, _UNRELATED_PARTY, False),
        _build_speaker("Bob Tan", 2, bob_party, False),
        _build_speaker("Cara Lim", 2, _UNRELATED_PARTY, False),
    ]
    scratch_session.add_all(speakers)
    scratch_session.commit()
    return speakers


def _get_stored_rows(scratch_session: Session, seeded: list[Speaker]) -> list[tuple[bool, str]]:
    scratch_session.expire_all()
    return [(speaker.is_legislative_assembly, speaker.party) for speaker in (scratch_session.get_one(Speaker, seeded_speaker.id) for seeded_speaker in seeded)]


_BEFORE = [(False, _UNRELATED_PARTY), (False, _OLD_PARTY), (False, _UNRELATED_PARTY)]
_AFTER = [(True, _UNRELATED_PARTY), (False, _NEW_PARTY), (False, _UNRELATED_PARTY)]


@pytest.fixture(autouse=True)
def _use_scratch_data(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apply_speaker_overrides_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_speaker_overrides_script, "get_speaker_overrides", lambda: _OVERRIDES)
    monkeypatch.setattr(apply_speaker_overrides_script, "get_colonial_members", lambda: [])


def test_dry_run_writes_the_plan_and_changes_no_row(scratch_session: Session, tmp_path: Path) -> None:
    seeded = _seed_speakers(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_speaker_overrides_script.apply_speaker_overrides(is_commit=False, plan_path=plan_path)

    plan = json.loads(plan_path.read_text())
    assert plan == {
        "flag_changes": [
            {
                "id": seeded[0].id,
                "name": "Ann Lee",
                "parliament_number": 1,
                "is_legislative_assembly_before": False,
                "is_legislative_assembly_after": True,
            }
        ],
        "party_changes": [
            {
                "id": seeded[1].id,
                "name": "Bob Tan",
                "parliament_number": 2,
                "party_before": _OLD_PARTY,
                "party_after": _NEW_PARTY,
            }
        ],
    }
    assert _get_stored_rows(scratch_session, seeded) == _BEFORE


def test_commit_refuses_after_a_stored_party_moves_off_both_values(scratch_session: Session) -> None:
    seeded = _seed_speakers(scratch_session, bob_party="Singapore People's Party")

    with pytest.raises(HansardWriteCheckError, match="stored party is neither the source value nor the override"):
        apply_speaker_overrides_script.apply_speaker_overrides(is_commit=True, plan_path=None)

    assert _get_stored_rows(scratch_session, seeded) == [(False, _UNRELATED_PARTY), (False, "Singapore People's Party"), (False, _UNRELATED_PARTY)]


def test_commit_on_an_unchanged_state_writes_exactly_the_plan(scratch_session: Session) -> None:
    seeded = _seed_speakers(scratch_session)

    apply_speaker_overrides_script.apply_speaker_overrides(is_commit=True, plan_path=None)

    assert _get_stored_rows(scratch_session, seeded) == _AFTER

    apply_speaker_overrides_script.apply_speaker_overrides(is_commit=True, plan_path=None)

    assert _get_stored_rows(scratch_session, seeded) == _AFTER


def test_commit_refuses_the_protected_local_port_and_writes_nothing(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seeded = _seed_speakers(scratch_session)
    monkeypatch.setattr(apply_speaker_overrides_script, "settings", SimpleNamespace(database_url=_PROTECTED_DATABASE_URL))

    with pytest.raises(HansardWriteTargetError, match="5432"):
        apply_speaker_overrides_script.apply_speaker_overrides(is_commit=True, plan_path=None)

    assert _get_stored_rows(scratch_session, seeded) == _BEFORE
