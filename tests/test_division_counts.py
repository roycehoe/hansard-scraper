import json
from pathlib import Path
from typing import Optional

import pytest

from crud.speech import SpeechParseRow
from enums import DivisionCountSource, SpeechKind, UnreadDivisionReason
from services.division import get_report_divisions

_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures" / "counts"
_REPORT_ID = 1
_LIST_ROW_COUNT = 3
_FILLER_ROW_COUNT = 4
_LINE_FIRST = "The House divided: Ayes, 10; Noes, 3."
_TOTAL_FIRST = "There are 10 Ayes and 3 Noes."
_FILLER_TEXT = "Order, order."
_LIST_NAME_TEXT = "A member's name"


def _build_row(
    ordinal: int, kind: Optional[str], speaker: Optional[str], transcript: str
) -> SpeechParseRow:
    return SpeechParseRow(
        id=ordinal,
        report_id=_REPORT_ID,
        ordinal=ordinal,
        speaker=speaker,
        transcript=transcript,
        kind=None if kind is None else SpeechKind(kind),
        speaker_id=None,
    )


def _build_rows(
    kinds_and_transcripts: list[tuple[Optional[str], str]],
) -> list[SpeechParseRow]:
    return [
        _build_row(ordinal, kind, None, transcript)
        for ordinal, (kind, transcript) in enumerate(kinds_and_transcripts, 1)
    ]


@pytest.mark.parametrize(
    "fixture_path",
    sorted(_FIXTURE_DIRECTORY.glob("*.json")),
    ids=lambda fixture_path: fixture_path.stem,
)
def test_golden_fixture(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    rows = [_build_row(*fixture_row) for fixture_row in fixture["rows"]]

    report_divisions = get_report_divisions(rows)

    assert len(report_divisions.divisions) == len(fixture["expected_divisions"])
    for division, expected in zip(
        report_divisions.divisions, fixture["expected_divisions"]
    ):
        assert division.report_division_number == expected["report_division_number"]
        assert division.speech_ordinal == expected["speech_ordinal"]
        assert division.count_source == DivisionCountSource(expected["count_source"])
        assert division.printed_counts == expected["printed_counts"]
        assert division.ayes == expected["ayes"]
        assert division.noes == expected["noes"]
        assert division.abstentions == expected["abstentions"]
        assert division.absent == expected["absent"]
        assert division.paired == expected["paired"]
        assert division.merged_total_ordinal == expected["merged_total_ordinal"]
    assert [
        (unread_row.speech_ordinal, unread_row.reason)
        for unread_row in report_divisions.unread_rows
    ] == [
        (expected["speech_ordinal"], UnreadDivisionReason(expected["reason"]))
        for expected in fixture["expected_unread"]
    ]


@pytest.mark.parametrize(
    ("kind", "transcript", "expected_counts"),
    [
        (
            "PROCEDURAL",
            "The House divided: Ayes, 36; Absent, 15.",
            (36, None, None, 15, None),
        ),
        (
            "PROCEDURAL",
            "The House divided: Ayes, 36 Absent, 15.",
            (36, None, None, 15, None),
        ),
        (
            "PROCEDURAL",
            "Division taken: Ayes 80, No Nil, Abstention Nil",
            (80, 0, 0, None, None),
        ),
        (
            "PROCEDURAL",
            "Question put: Ayes, 1 ; Noes, 36; Abstentions, 1.",
            (1, 36, 1, None, None),
        ),
        (
            "SPEECH",
            "There are seven Ayes, Nine Noes and nil Abstentions.",
            (7, 9, 0, None, None),
        ),
        (
            "SPEECH",
            "The result of the Division is: 27 Ayes; 1 No; 3 Absent.",
            (27, 1, None, 3, None),
        ),
        (
            "SPEECH",
            "36 Ayes, 15 Absent. I declare the motion carried.",
            (36, None, None, 15, None),
        ),
        (
            "SPEECH",
            "There are 77 Ayes and no Noes.",
            (77, 0, None, None, None),
        ),
        (
            "SPEECH",
            "The result of the voting is 23 Ayes, 23 Noes, 3 Absent, and 2 Paired.",
            (23, 23, None, 3, 2),
        ),
    ],
)
def test_counts_of_a_single_row(
    kind: str, transcript: str, expected_counts: tuple[Optional[int], ...]
) -> None:
    report_divisions = get_report_divisions(_build_rows([(kind, transcript)]))

    assert len(report_divisions.divisions) == 1
    division = report_divisions.divisions[0]
    assert (
        division.ayes,
        division.noes,
        division.abstentions,
        division.absent,
        division.paired,
    ) == expected_counts
    assert report_divisions.unread_rows == []


@pytest.mark.parametrize(
    ("kind", "transcript"),
    [
        ("SPEECH", "There are now 31 votes to be accounted for."),
        ("SPEECH", "There are amendments which will be made as a matter of course."),
        ("SPEECH", 'To the contrary say "No". I think the "Ayes" have it'),
        ("PROCEDURAL", "Question put, and agreed to."),
        ("PROCEDURAL", "Division Bells rung."),
        ("SPEECH", "Ayes, 12; Noes, 3."),
    ],
)
def test_row_that_is_not_a_division_makes_none(kind: str, transcript: str) -> None:
    report_divisions = get_report_divisions(_build_rows([(kind, transcript)]))

    assert report_divisions.divisions == []
    assert report_divisions.unread_rows == []


def test_row_starting_with_a_count_of_noes_is_not_a_division() -> None:
    report_divisions = get_report_divisions(
        _build_rows([("SPEECH", "3 Noes and 36 Ayes.")])
    )

    assert report_divisions.divisions == []


@pytest.mark.parametrize(
    "transcript",
    [
        "The House divided: Ayes, 36.",
        "The House divided: Noes, 3; Absent, 1.",
    ],
)
def test_opening_that_reads_no_division_span_is_unread(transcript: str) -> None:
    report_divisions = get_report_divisions(_build_rows([("PROCEDURAL", transcript)]))

    assert report_divisions.divisions == []
    assert [unread_row.reason for unread_row in report_divisions.unread_rows] == [
        UnreadDivisionReason.OPENING_WITHOUT_COUNTS
    ]


def test_repeated_label_is_unread() -> None:
    report_divisions = get_report_divisions(
        _build_rows([("PROCEDURAL", "The House divided: Ayes, 3; Ayes, 4; Noes, 1")])
    )

    assert report_divisions.divisions == []
    assert [unread_row.reason for unread_row in report_divisions.unread_rows] == [
        UnreadDivisionReason.REPEATED_COUNT_LABEL
    ]


@pytest.mark.parametrize(
    "transcript",
    [
        "The House divided: Ayes, Nil; Noes, 2; Absentions, 31; Absent, 17.",
        "The House divided: Ayes, Nil; Noes, 2; Absentation, 31; Absent, 17.",
    ],
)
def test_misprinted_abstentions_label_is_read_with_the_counts_after_it(
    transcript: str,
) -> None:
    report_divisions = get_report_divisions(_build_rows([("PROCEDURAL", transcript)]))

    (division,) = report_divisions.divisions
    assert (
        division.ayes,
        division.noes,
        division.abstentions,
        division.absent,
        division.paired,
    ) == (0, 2, 31, 17, None)
    assert division.printed_counts == transcript.rstrip(".")


def test_count_after_an_unknown_label_makes_the_line_unread() -> None:
    report_divisions = get_report_divisions(
        _build_rows(
            [("PROCEDURAL", "The House divided: Ayes, 10; Noes, 3; Abstainers, 4.")]
        )
    )

    assert report_divisions.divisions == []
    assert [unread_row.reason for unread_row in report_divisions.unread_rows] == [
        UnreadDivisionReason.COUNT_AFTER_READ_COUNTS
    ]


def test_opening_in_unclassified_row_is_unread() -> None:
    report_divisions = get_report_divisions(
        _build_rows([("UNCLASSIFIED", "The House divided: Ayes, 3; Noes, 4")])
    )

    assert report_divisions.divisions == []
    assert [unread_row.reason for unread_row in report_divisions.unread_rows] == [
        UnreadDivisionReason.OPENING_IN_ROW_OF_OTHER_KIND
    ]


def _build_window_rows(filler_row_count: int) -> list[SpeechParseRow]:
    return _build_rows(
        [("PROCEDURAL", _LINE_FIRST)]
        + [("UNCLASSIFIED", _LIST_NAME_TEXT)] * _LIST_ROW_COUNT
        + [("SPEECH", _FILLER_TEXT)] * filler_row_count
        + [("SPEECH", _TOTAL_FIRST)]
    )


def test_merge_window_is_five_rows_from_the_last_list_row() -> None:
    merged = get_report_divisions(_build_window_rows(_FILLER_ROW_COUNT))
    apart = get_report_divisions(_build_window_rows(_FILLER_ROW_COUNT + 1))

    assert len(merged.divisions) == 1
    assert merged.divisions[0].count_source == DivisionCountSource.PRINTED_LINE
    assert [division.count_source for division in apart.divisions] == [
        DivisionCountSource.PRINTED_LINE,
        DivisionCountSource.SPOKEN_TOTAL,
    ]


def test_another_division_line_between_blocks_the_merge() -> None:
    report_divisions = get_report_divisions(
        _build_rows(
            [
                ("PROCEDURAL", _LINE_FIRST),
                ("SPEECH", _FILLER_TEXT),
                ("PROCEDURAL", "The House divided: Ayes, 20; Noes, 4."),
                ("SPEECH", "There are 20 Ayes and 4 Noes."),
            ]
        )
    )

    assert [
        division.merged_total_ordinal for division in report_divisions.divisions
    ] == [
        None,
        4,
    ]
    assert [division.ayes for division in report_divisions.divisions] == [10, 20]


def test_merged_total_ordinal_is_the_totals_row_or_none() -> None:
    merged = get_report_divisions(_build_window_rows(_FILLER_ROW_COUNT))
    apart = get_report_divisions(_build_window_rows(_FILLER_ROW_COUNT + 1))
    alone = get_report_divisions(_build_rows([("PROCEDURAL", _LINE_FIRST)]))

    total_ordinal = 1 + _LIST_ROW_COUNT + _FILLER_ROW_COUNT + 1
    assert merged.divisions[0].merged_total_ordinal == total_ordinal
    assert [division.merged_total_ordinal for division in apart.divisions] == [
        None,
        None,
    ]
    assert alone.divisions[0].merged_total_ordinal is None


def test_counts_that_differ_stand_on_the_printed_line_and_flag_the_total() -> None:
    report_divisions = get_report_divisions(
        _build_rows(
            [
                ("PROCEDURAL", "The House divided: Ayes, 10; Noes, 3"),
                ("SPEECH", "There are 11 Ayes and 3 Noes."),
            ]
        )
    )

    assert len(report_divisions.divisions) == 1
    assert (report_divisions.divisions[0].ayes, report_divisions.divisions[0].noes) == (
        10,
        3,
    )
    assert [
        (unread_row.speech_ordinal, unread_row.reason)
        for unread_row in report_divisions.unread_rows
    ] == [(2, UnreadDivisionReason.MERGED_COUNTS_DIFFER)]


def test_a_total_with_differing_counts_still_sets_the_merged_total_ordinal() -> None:
    report_divisions = get_report_divisions(
        _build_rows(
            [
                ("PROCEDURAL", "The House divided: Ayes, 10; Noes, 3"),
                ("SPEECH", "There are 11 Ayes and 3 Noes."),
            ]
        )
    )

    assert [
        division.merged_total_ordinal for division in report_divisions.divisions
    ] == [2]
    assert [
        (unread_row.speech_ordinal, unread_row.reason)
        for unread_row in report_divisions.unread_rows
    ] == [(2, UnreadDivisionReason.MERGED_COUNTS_DIFFER)]
