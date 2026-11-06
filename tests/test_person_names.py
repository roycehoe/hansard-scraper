from collections import Counter
from types import SimpleNamespace
from typing import Optional

import pytest
from pydantic import ValidationError
from sqlmodel import Session

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.person import CRUDPerson
from crud.person_name_spelling import CRUDPersonNameSpelling
from crud.speaker import CRUDSpeaker
from database.person import Person
from database.speaker import Speaker
from enums import PersonDecisionKind, PersonNameSpellingKind
from exceptions import HansardDataFileError
from populate import persons as populate_persons_module
from populate.persons import populate_persons
from schemas.person_decision import PersonDecision, PersonDecisionMember
from schemas.person_name_spelling import PersonNameSpellingEntry
from services.person import build_person_name_spellings, cluster_speakers
from utils.data_files import get_person_decisions, get_person_name_spellings

_NAME_DECISION_COUNT = 13
_SPELLING_NOTE_PERSON_COUNT = 14
_RENAMED_PERSON_NAMES = frozenset(
    {
        "Koo Young",
        "Lai Tha Chai",
        "Zulkifli Bin Mohammed",
        "Ahmad Khalis bin Abdul Ghani",
        "Abdul Nasser Bin Kamaruddin",
        "Baharudin Bin Mohamed Ariff",
        "Chew Chin Han",
    }
)
_SOURCE_LINK = "[a source](https://example.org/source)"


def _get_speaker(
    speaker_id: int, name: str, parliament_number: int, person_id: Optional[int] = None
) -> Speaker:
    return Speaker(
        id=speaker_id,
        name=name,
        party="People's Action Party",
        is_legislative_assembly=False,
        parliament_number=parliament_number,
        person_id=person_id,
    )


def _get_decision(
    name: str,
    parliament_number: int,
    kind: PersonDecisionKind,
    person_name: Optional[str],
) -> PersonDecision:
    return PersonDecision(
        person_name=person_name,
        members=[PersonDecisionMember(name=name, parliament_number=parliament_number)],
        decision=kind,
        source="test",
    )


def _get_spelling_entry(
    name: str,
    spelling: str,
    kind: PersonNameSpellingKind,
    note: str = _SOURCE_LINK,
) -> PersonNameSpellingEntry:
    return PersonNameSpellingEntry(
        member=PersonDecisionMember(name=name, parliament_number=5),
        spelling=spelling,
        kind=kind,
        note=note,
    )


def _get_canonical_names(
    speakers: list[Speaker], decisions: list[PersonDecision]
) -> list[str]:
    return [
        person_cluster.canonical_name
        for person_cluster in cluster_speakers(speakers, decisions).clusters
    ]


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
def test_canonical_name_is_given_surname_without_honorific_or_decoration(
    source_name: str, canonical_name: str
) -> None:
    assert _get_canonical_names([_get_speaker(1, source_name, 5)], []) == [
        canonical_name
    ]


def test_comma_and_natural_spellings_of_one_person_give_one_natural_name() -> None:
    speakers = [
        _get_speaker(1, "Tan Keng Yam, Tony", 5),
        _get_speaker(2, "Tony Tan Keng Yam", 6),
    ]

    assert _get_canonical_names(speakers, []) == ["Tony Tan Keng Yam"]


def test_name_decision_replaces_the_rule_for_its_person() -> None:
    speakers = [
        _get_speaker(1, "Devan Nair, Mrs", 1),
        _get_speaker(2, "Tay S C, Simon, Assoc Prof", 9),
    ]
    decisions = [
        _get_decision("Devan Nair, Mrs", 1, PersonDecisionKind.NAME, "Mrs Devan Nair")
    ]

    assert _get_canonical_names(speakers, decisions) == [
        "Mrs Devan Nair",
        "Simon Tay S C",
    ]


def test_spelling_decisions_give_the_official_report_form() -> None:
    speakers = [
        _get_speaker(1, "Seet Ai Mei, Dr", 7),
        _get_speaker(2, "Mohamed Maidin BPM", 8),
        _get_speaker(3, "Mohamed Maidin BPM", 9),
    ]
    decisions = [
        _get_decision("Seet Ai Mei, Dr", 7, PersonDecisionKind.NAME, "Seet Ai Mee"),
        _get_decision(
            "Mohamed Maidin BPM", 8, PersonDecisionKind.NAME, "Mohamad Maidin"
        ),
    ]

    assert _get_canonical_names(speakers, decisions) == [
        "Seet Ai Mee",
        "Mohamad Maidin",
    ]


def test_name_decision_does_not_merge_or_split_clusters() -> None:
    speakers = [
        _get_speaker(1, "Yeo Yong-Boon, George", 7),
        _get_speaker(2, "Yeo Yong-Boon, George", 8),
    ]
    decisions = [
        _get_decision(
            "Yeo Yong-Boon, George", 7, PersonDecisionKind.NAME, "George Yong-Boon Yeo"
        )
    ]

    cluster_result = cluster_speakers(speakers, decisions)

    assert [
        len(person_cluster.memberships) for person_cluster in cluster_result.clusters
    ] == [2]
    assert _get_canonical_names(speakers, decisions) == ["George Yong-Boon Yeo"]


def test_decision_naming_no_speaker_row_raises_data_file_error() -> None:
    decisions = [
        _get_decision("No Such Member", 7, PersonDecisionKind.NAME, "No Such Member")
    ]

    with pytest.raises(
        HansardDataFileError, match="data/person_decisions.json names no speaker row"
    ):
        cluster_speakers([_get_speaker(1, "Yeo Yong-Boon, George", 7)], decisions)


def test_refused_merge_decision_raises_data_file_error() -> None:
    members = [
        PersonDecisionMember(name="Ong Teng Cheong", parliament_number=7),
        PersonDecisionMember(name="Ong Pang Boon", parliament_number=7),
    ]
    decisions = [
        PersonDecision(
            person_name=None,
            members=members,
            decision=PersonDecisionKind.MERGE,
            source="test",
        )
    ]
    speakers = [
        _get_speaker(1, "Ong Teng Cheong", 7),
        _get_speaker(2, "Ong Pang Boon", 7),
    ]

    with pytest.raises(
        HansardDataFileError, match="data/person_decisions.json merge decision refused"
    ):
        cluster_speakers(speakers, decisions)


def test_data_file_gives_each_name_decision_one_member_and_a_name() -> None:
    name_decisions = [
        decision
        for decision in get_person_decisions()
        if decision.decision == PersonDecisionKind.NAME
    ]

    assert len(name_decisions) == _NAME_DECISION_COUNT
    assert all(
        len(decision.members) == 1 and decision.person_name and decision.source
        for decision in name_decisions
    )


def test_data_file_renames_seven_persons_and_leaves_lim_to_the_rule() -> None:
    person_names = {decision.person_name for decision in get_person_decisions()}

    assert _RENAMED_PERSON_NAMES <= person_names
    assert "Lim Chin Siong" not in person_names


def test_data_file_gives_each_noted_person_one_canonical_row_first() -> None:
    entries = get_person_name_spellings()
    member_to_entries: dict[PersonDecisionMember, list[PersonNameSpellingEntry]] = {}
    for entry in entries:
        member_to_entries.setdefault(entry.member, []).append(entry)

    assert len(member_to_entries) == _SPELLING_NOTE_PERSON_COUNT
    for member_entries in member_to_entries.values():
        assert member_entries[0].kind == PersonNameSpellingKind.CANONICAL
        kind_to_count = Counter(entry.kind for entry in member_entries)
        assert kind_to_count[PersonNameSpellingKind.CANONICAL] == 1
        assert len(member_entries) > 1


def test_data_file_uses_each_spelling_once() -> None:
    entries = get_person_name_spellings()

    assert len({(entry.member, entry.spelling) for entry in entries}) == len(entries)


def test_data_file_holds_the_name_of_every_renamed_person() -> None:
    canonical_spellings = {
        entry.spelling
        for entry in get_person_name_spellings()
        if entry.kind == PersonNameSpellingKind.CANONICAL
    }

    assert _RENAMED_PERSON_NAMES | {"Lim Ching Siong"} <= canonical_spellings


@pytest.mark.parametrize(
    "note",
    [
        "A sentence with no link.",
        "[a source](http://example.org/source)",
        f"{_SOURCE_LINK} and [a script](javascript:alert)",
    ],
)
def test_spelling_note_needs_a_safe_link_for_every_source(note: str) -> None:
    with pytest.raises(ValidationError):
        _get_spelling_entry(
            "Koo Yong", "Koo Yong", PersonNameSpellingKind.OTHER_SPELLING, note
        )


def test_spelling_note_may_link_a_report_page() -> None:
    entry = _get_spelling_entry(
        "Koo Yong",
        "Koo Yong",
        PersonNameSpellingKind.OTHER_SPELLING,
        "Printed by [Hansard](/reports/00069147-ZZ.00052491-ZZ_1#id030_19660817-bill).",
    )

    assert entry.spelling == "Koo Yong"


def test_build_person_name_spellings_numbers_each_person_in_file_order() -> None:
    entries = [
        _get_spelling_entry("Koo Yong", "Koo Young", PersonNameSpellingKind.CANONICAL),
        _get_spelling_entry("Lai Tai", "Lai Tha", PersonNameSpellingKind.CANONICAL),
        _get_spelling_entry(
            "Koo Yong", "Koo Yong", PersonNameSpellingKind.OTHER_SPELLING
        ),
    ]

    person_name_spellings = build_person_name_spellings(
        entries,
        {("Koo Yong", 5): 1, ("Lai Tai", 5): 2},
        {1: "Koo Young", 2: "Lai Tha"},
    )

    assert [
        (row.person_id, row.ordinal, row.spelling) for row in person_name_spellings
    ] == [(1, 1, "Koo Young"), (2, 1, "Lai Tha"), (1, 2, "Koo Yong")]


def test_spelling_entry_naming_no_speaker_row_raises_data_file_error() -> None:
    entries = [
        _get_spelling_entry("No Such", "No Such", PersonNameSpellingKind.CANONICAL)
    ]

    with pytest.raises(
        HansardDataFileError,
        match="data/person_name_spellings.json names no speaker row",
    ):
        build_person_name_spellings(entries, {}, {})


@pytest.mark.parametrize(
    ("spelling", "kind"),
    [
        ("Koo Yong", PersonNameSpellingKind.CANONICAL),
        ("Koo Young", PersonNameSpellingKind.OTHER_SPELLING),
    ],
)
def test_canonical_entry_must_be_the_name_the_person_has(
    spelling: str, kind: PersonNameSpellingKind
) -> None:
    entries = [_get_spelling_entry("Koo Yong", spelling, kind)]

    with pytest.raises(HansardDataFileError, match="for person 1, named 'Koo Young'"):
        build_person_name_spellings(entries, {("Koo Yong", 5): 1}, {1: "Koo Young"})


def test_populate_persons_stores_spellings_and_a_second_run_changes_nothing(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch_session.add(_get_speaker(1, "Koo Yong", 5))
    scratch_session.commit()
    monkeypatch.setattr(
        populate_persons_module,
        "get_person_decisions",
        lambda: [_get_decision("Koo Yong", 5, PersonDecisionKind.NAME, "Koo Young")],
    )
    monkeypatch.setattr(
        populate_persons_module,
        "get_person_name_spellings",
        lambda: [
            _get_spelling_entry(
                "Koo Yong", "Koo Young", PersonNameSpellingKind.CANONICAL
            ),
            _get_spelling_entry(
                "Koo Yong", "Koo Yong", PersonNameSpellingKind.OTHER_SPELLING
            ),
        ],
    )

    populate_persons(scratch_session)
    first_run = [
        (row.id, row.ordinal, row.spelling, row.kind)
        for row in CRUDPersonNameSpelling(scratch_session).get_all()
    ]
    populate_persons(scratch_session)
    second_run = [
        (row.id, row.ordinal, row.spelling, row.kind)
        for row in CRUDPersonNameSpelling(scratch_session).get_all()
    ]

    assert second_run == first_run
    assert [row[1:3] for row in first_run] == [(1, "Koo Young"), (2, "Koo Yong")]


def test_populate_persons_replaces_spellings_when_the_file_changes(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch_session.add(_get_speaker(1, "Koo Yong", 5))
    scratch_session.commit()
    monkeypatch.setattr(populate_persons_module, "get_person_decisions", lambda: [])
    monkeypatch.setattr(
        populate_persons_module,
        "get_person_name_spellings",
        lambda: [
            _get_spelling_entry(
                "Koo Yong", "Koo Yong", PersonNameSpellingKind.CANONICAL
            )
        ],
    )
    populate_persons(scratch_session)
    monkeypatch.setattr(
        populate_persons_module,
        "get_person_name_spellings",
        lambda: [
            _get_spelling_entry(
                "Koo Yong",
                "Koo Yong",
                PersonNameSpellingKind.CANONICAL,
                "[another source](https://example.org/other)",
            )
        ],
    )

    populate_persons(scratch_session)

    assert [row.note for row in CRUDPersonNameSpelling(scratch_session).get_all()] == [
        "[another source](https://example.org/other)"
    ]


def test_populate_persons_renames_a_reused_person_and_leaves_an_unchanged_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    speakers = [
        _get_speaker(1, "Rajaratnam, S", 2, person_id=10),
        _get_speaker(2, "Lee Kuan Yew", 2, person_id=11),
        _get_speaker(3, "Goh Chok Tong", 2),
    ]
    persons = [
        Person(id=10, canonical_name="Rajaratnam, S", basis="single"),
        Person(id=11, canonical_name="Lee Kuan Yew", basis="single"),
    ]
    renamed: list[tuple[int, str]] = []
    created: list[str] = []
    linked: list[dict[int, int]] = []
    monkeypatch.setattr(populate_persons_module, "get_person_decisions", lambda: [])
    monkeypatch.setattr(
        populate_persons_module, "get_person_name_spellings", lambda: []
    )
    monkeypatch.setattr(CRUDPersonNameSpelling, "get_all", lambda self: [])
    monkeypatch.setattr(CRUDSpeaker, "get_all", lambda self: speakers)
    monkeypatch.setattr(
        CRUDSpeaker, "set_person_ids_bulk", lambda self, updates: linked.append(updates)
    )
    monkeypatch.setattr(CRUDPerson, "get_all", lambda self: persons)
    monkeypatch.setattr(
        CRUDPerson,
        "create",
        lambda self, person: created.append(person.canonical_name) or 12,
    )
    monkeypatch.setattr(
        CRUDPerson,
        "set_canonical_name",
        lambda self, person, canonical_name: renamed.append(
            (person.id, canonical_name)
        ),
    )

    populate_persons(SimpleNamespace(commit=lambda: None))

    assert renamed == [(10, "S Rajaratnam")]
    assert created == ["Goh Chok Tong"]
    assert linked == [{3: 12}]


def test_populate_persons_recomputes_the_basis_of_a_reused_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    speakers = [
        _get_speaker(1, "Lee Li Lian", 12, person_id=10),
        _get_speaker(2, "Lee Li Lian", 13),
    ]
    persons = [Person(id=10, canonical_name="Lee Li Lian", basis="single")]
    basis_changes: list[tuple[int, str]] = []
    created: list[str] = []
    linked: list[dict[int, int]] = []
    monkeypatch.setattr(populate_persons_module, "get_person_decisions", lambda: [])
    monkeypatch.setattr(
        populate_persons_module, "get_person_name_spellings", lambda: []
    )
    monkeypatch.setattr(CRUDPersonNameSpelling, "get_all", lambda self: [])
    monkeypatch.setattr(CRUDSpeaker, "get_all", lambda self: speakers)
    monkeypatch.setattr(
        CRUDSpeaker, "set_person_ids_bulk", lambda self, updates: linked.append(updates)
    )
    monkeypatch.setattr(CRUDPerson, "get_all", lambda self: persons)
    monkeypatch.setattr(
        CRUDPerson,
        "create",
        lambda self, person: created.append(person.canonical_name) or 11,
    )
    monkeypatch.setattr(
        CRUDPerson,
        "set_basis",
        lambda self, person, basis: basis_changes.append((person.id, basis)),
    )

    populate_persons(SimpleNamespace(commit=lambda: None))

    assert basis_changes == [(10, "auto:exact")]
    assert created == []
    assert linked == [{2: 10}]
