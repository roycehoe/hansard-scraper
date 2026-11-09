from datetime import datetime

from sqlmodel import Session

from crud.speech import CRUDSpeech
from enums import ReportType, SpeechKind
from services.bill import (
    FIRST_READING_PATTERN,
    NOT_FIRST_READING_PATTERNS,
    NOT_THIRD_READING_PATTERNS,
    SECOND_READING_AGREED_PATTERN,
    SECOND_READING_PATTERN,
    THIRD_READING_PATTERN,
)
from tests.bill_seed import seed_bill_report, seed_speech

_STAGE_LINE_KINDS = (SpeechKind.PROCEDURAL, SpeechKind.UNCLASSIFIED)
_SITTING_DATE = datetime(2024, 11, 12)


def _get_matched_texts(
    session: Session,
    lines: list[str],
    pattern: str,
    not_patterns: tuple[str, ...],
) -> list[str]:
    report_id = seed_bill_report(
        session, "match-report", ReportType.BILL, _SITTING_DATE, "Food Bill", []
    )
    for ordinal, line in enumerate(lines, start=1):
        seed_speech(
            session, report_id, ordinal, None, None, SpeechKind.PROCEDURAL, line
        )
    return [
        ordinal_transcript_row.transcript
        for ordinal_transcript_row in CRUDSpeech(
            session
        ).get_ordinal_transcript_rows_by_report_ids_and_kinds_and_transcript_regex_and_transcript_not_regexes(
            [report_id], _STAGE_LINE_KINDS, pattern, not_patterns
        )
    ]


def test_the_first_reading_pattern_keeps_the_printed_line_and_drops_the_near_misses(
    scratch_session: Session,
) -> None:
    lines = [
        "Bill read a First time.",
        "Bill brought up, and read the First time.",
        "The Bill was read a First time on 5 March.",
        "Clause read a Second time and added to the Bill.",
    ]

    matched_texts = _get_matched_texts(
        scratch_session, lines, FIRST_READING_PATTERN, NOT_FIRST_READING_PATTERNS
    )

    assert matched_texts == ["Bill read a First time."]


def test_the_second_reading_order_pattern_keeps_only_the_order_line(
    scratch_session: Session,
) -> None:
    lines = [
        "Order for Second Reading read.",
        "That the Bill be now read a Second time.",
        "Clause read a Second time and added to the Bill.",
    ]

    matched_texts = _get_matched_texts(
        scratch_session, lines, SECOND_READING_PATTERN, ()
    )

    assert matched_texts == ["Order for Second Reading read."]


def test_the_second_reading_agreed_pattern_keeps_only_the_accordingly_line(
    scratch_session: Session,
) -> None:
    accordingly_line = (
        "Bill accordingly read a Second time and committed to a Committee of the whole House."
    )
    lines = [
        accordingly_line,
        "That the Bill be now read a Second time.",
        "Clause read a Second time and added to the Bill.",
        "Bill read a Second time and committed to a Committee of the whole House.",
    ]

    matched_texts = _get_matched_texts(
        scratch_session, lines, SECOND_READING_AGREED_PATTERN, ()
    )

    assert matched_texts == [accordingly_line]


def test_the_third_reading_pattern_keeps_the_passed_line_and_drops_the_motion_forms(
    scratch_session: Session,
) -> None:
    lines = [
        "Bill read a Third time and passed.",
        "That the Bill be now read a Third time.",
        "I beg to move, That the Bill be read a Third time.",
    ]

    matched_texts = _get_matched_texts(
        scratch_session, lines, THIRD_READING_PATTERN, NOT_THIRD_READING_PATTERNS
    )

    assert matched_texts == ["Bill read a Third time and passed."]


def test_a_speech_line_never_proves_a_stage(scratch_session: Session) -> None:
    report_id = seed_bill_report(
        scratch_session, "speech-report", ReportType.BILL, _SITTING_DATE, "Food Bill", []
    )
    for ordinal, kind in enumerate(
        (SpeechKind.SPEECH, SpeechKind.DOCUMENT_TEXT), start=1
    ):
        seed_speech(
            scratch_session,
            report_id,
            ordinal,
            None,
            None,
            kind,
            "Bill read a Third time and passed.",
        )

    rows = CRUDSpeech(
        scratch_session
    ).get_ordinal_transcript_rows_by_report_ids_and_kinds_and_transcript_regex_and_transcript_not_regexes(
        [report_id], _STAGE_LINE_KINDS, THIRD_READING_PATTERN, NOT_THIRD_READING_PATTERNS
    )

    assert rows == []
