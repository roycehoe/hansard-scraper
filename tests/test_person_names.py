from types import SimpleNamespace
from typing import Optional

import pytest

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.person import CRUDPerson
from crud.speaker import CRUDSpeaker
from database.person import Person
from database.speaker import Speaker
from enums import PersonDecisionKind
from exceptions import HansardDataFileError
from populate import persons as populate_persons_module
from populate.persons import populate_persons
from schemas.person_decision import PersonDecision, PersonDecisionMember
from services.person import cluster_speakers
from utils.data_files import get_person_decisions

_NAME_DECISION_COUNT = 6


def _get_speaker(speaker_id: int, name: str, parliament_number: int, person_id: Optional[int] = None) -> Speaker:
    return Speaker(
        id=speaker_id,
        name=name,
        party="People's Action Party",
        is_legislative_assembly=False,
        parliament_number=parliament_number,
        person_id=person_id,
    )


def _get_decision(name: str, parliament_number: int, kind: PersonDecisionKind, person_name: Optional[str]) -> PersonDecision:
    return PersonDecision(
        person_name=person_name,
        members=[PersonDecisionMember(name=name, parliament_number=parliament_number)],
        decision=kind,
        source="test",
    )


def _get_canonical_names(speakers: list[Speaker], decisions: list[PersonDecision]) -> list[str]:
    return [person_cluster.canonical_name for person_cluster in cluster_speakers(speakers, decisions).clusters]


@pytest.mark.parametrize(
    ("source_name", "canonical_name"),
    [
        ("Rajaratnam, S", "S Rajaratnam"),
        ("Tan Keng Yam, Tony", "Tony Tan Keng Yam"),
        ("Chau Sik Ting, Dr", "Chau Sik Ting"),
        ("Choo, Maurice, Assoc Prof", "Maurice Choo"),
        ("Mohamed Maidin BPM", "Mohamed Maidin"),
        ("Lee Hong Chuang BBM", "Lee Hong Chuang"),
        ("Lee Kuan Yew", "Lee Kuan Yew"),
    ],
)
def test_canonical_name_is_given_surname_without_honorific_or_decoration(source_name: str, canonical_name: str) -> None:
    assert _get_canonical_names([_get_speaker(1, source_name, 5)], []) == [canonical_name]


def test_comma_and_natural_spellings_of_one_person_give_one_natural_name() -> None:
    speakers = [_get_speaker(1, "Tan Keng Yam, Tony", 5), _get_speaker(2, "Tony Tan Keng Yam", 6)]

    assert _get_canonical_names(speakers, []) == ["Tony Tan Keng Yam"]


def test_name_decision_replaces_the_rule_for_its_person() -> None:
    speakers = [_get_speaker(1, "Devan Nair, Mrs", 1), _get_speaker(2, "Tay S C, Simon, Assoc Prof", 9)]
    decisions = [_get_decision("Devan Nair, Mrs", 1, PersonDecisionKind.NAME, "Mrs Devan Nair")]

    assert _get_canonical_names(speakers, decisions) == ["Mrs Devan Nair", "Simon Tay S C"]


def test_spelling_decisions_give_the_official_report_form() -> None:
    speakers = [
        _get_speaker(1, "Seet Ai Mei, Dr", 7),
        _get_speaker(2, "Mohamed Maidin BPM", 8),
        _get_speaker(3, "Mohamed Maidin BPM", 9),
    ]
    decisions = [
        _get_decision("Seet Ai Mei, Dr", 7, PersonDecisionKind.NAME, "Seet Ai Mee"),
        _get_decision("Mohamed Maidin BPM", 8, PersonDecisionKind.NAME, "Mohamad Maidin"),
    ]

    assert _get_canonical_names(speakers, decisions) == ["Seet Ai Mee", "Mohamad Maidin"]


def test_name_decision_does_not_merge_or_split_clusters() -> None:
    speakers = [_get_speaker(1, "Yeo Yong-Boon, George", 7), _get_speaker(2, "Yeo Yong-Boon, George", 8)]
    decisions = [_get_decision("Yeo Yong-Boon, George", 7, PersonDecisionKind.NAME, "George Yong-Boon Yeo")]

    cluster_result = cluster_speakers(speakers, decisions)

    assert [len(person_cluster.memberships) for person_cluster in cluster_result.clusters] == [2]
    assert _get_canonical_names(speakers, decisions) == ["George Yong-Boon Yeo"]


def test_decision_naming_no_speaker_row_raises_data_file_error() -> None:
    decisions = [_get_decision("No Such Member", 7, PersonDecisionKind.NAME, "No Such Member")]

    with pytest.raises(HansardDataFileError, match="data/person_decisions.json names no speaker row"):
        cluster_speakers([_get_speaker(1, "Yeo Yong-Boon, George", 7)], decisions)


def test_refused_merge_decision_raises_data_file_error() -> None:
    members = [PersonDecisionMember(name="Ong Teng Cheong", parliament_number=7), PersonDecisionMember(name="Ong Pang Boon", parliament_number=7)]
    decisions = [PersonDecision(person_name=None, members=members, decision=PersonDecisionKind.MERGE, source="test")]
    speakers = [_get_speaker(1, "Ong Teng Cheong", 7), _get_speaker(2, "Ong Pang Boon", 7)]

    with pytest.raises(HansardDataFileError, match="data/person_decisions.json merge decision refused"):
        cluster_speakers(speakers, decisions)


def test_data_file_gives_each_name_decision_one_member_and_a_name() -> None:
    name_decisions = [decision for decision in get_person_decisions() if decision.decision == PersonDecisionKind.NAME]

    assert len(name_decisions) == _NAME_DECISION_COUNT
    assert all(len(decision.members) == 1 and decision.person_name and decision.source for decision in name_decisions)


def test_populate_persons_renames_a_reused_person_and_leaves_an_unchanged_one(monkeypatch: pytest.MonkeyPatch) -> None:
    speakers = [
        _get_speaker(1, "Rajaratnam, S", 2, person_id=10),
        _get_speaker(2, "Lee Kuan Yew", 2, person_id=11),
        _get_speaker(3, "Goh Chok Tong", 2),
    ]
    persons = [Person(id=10, canonical_name="Rajaratnam, S"), Person(id=11, canonical_name="Lee Kuan Yew")]
    renamed: list[tuple[int, str]] = []
    created: list[str] = []
    linked: list[dict[int, int]] = []
    monkeypatch.setattr(populate_persons_module, "get_person_decisions", lambda: [])
    monkeypatch.setattr(CRUDSpeaker, "get_all", lambda self: speakers)
    monkeypatch.setattr(CRUDSpeaker, "set_person_ids_bulk", lambda self, updates: linked.append(updates))
    monkeypatch.setattr(CRUDPerson, "get_all", lambda self: persons)
    monkeypatch.setattr(CRUDPerson, "create", lambda self, person: created.append(person.canonical_name) or 12)
    monkeypatch.setattr(CRUDPerson, "set_canonical_name", lambda self, person, canonical_name: renamed.append((person.id, canonical_name)))

    populate_persons(SimpleNamespace(commit=lambda: None))

    assert renamed == [(10, "S Rajaratnam")]
    assert created == ["Goh Chok Tong"]
    assert linked == [{3: 12}]
