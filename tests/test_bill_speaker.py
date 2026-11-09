from datetime import datetime

import pytest

from crud.bill_report import BillReportSittingDateReportTypeRow
from crud.speech import SpeechOrdinalLabelRow, SpeechOrdinalTranscriptRow
from enums import BillReportRole, BillStage
from exceptions import HansardBillKeyError
from services.bill_speaker import (
    build_bill_report_speakers,
    build_bill_stage_lines,
    get_bill_key,
)


def _bill_report_row(
    report_id: int, sprs_report_id: str, sitting_date: datetime, role: BillReportRole
) -> BillReportSittingDateReportTypeRow:
    return BillReportSittingDateReportTypeRow(
        1, report_id, sprs_report_id, sitting_date, "bill", role
    )


def test_the_key_is_the_earliest_reading_report() -> None:
    later_row = _bill_report_row(
        1, "30000", datetime(2025, 1, 8), BillReportRole.READING
    )
    earlier_row = _bill_report_row(
        2, "20000", datetime(2024, 11, 12), BillReportRole.READING
    )

    assert get_bill_key(1, [later_row, earlier_row]) == "20000"
    assert get_bill_key(1, [earlier_row, later_row]) == "20000"


def test_a_tie_on_the_sitting_date_goes_to_the_lower_sprs_report_id_in_byte_order() -> (
    None
):
    sitting_date = datetime(2024, 11, 12)
    rows = [
        _bill_report_row(1, "9", sitting_date, BillReportRole.READING),
        _bill_report_row(2, "10753", sitting_date, BillReportRole.READING),
    ]

    assert get_bill_key(1, rows) == "10753"


def test_a_budget_debate_report_never_gives_the_key() -> None:
    rows = [
        _bill_report_row(
            1, "10000", datetime(2024, 3, 1), BillReportRole.BUDGET_DEBATE
        ),
        _bill_report_row(2, "20000", datetime(2024, 11, 12), BillReportRole.READING),
    ]

    assert get_bill_key(1, rows) == "20000"


def test_a_bill_with_no_reading_report_raises_the_key_error() -> None:
    budget_row = _bill_report_row(
        1, "10000", datetime(2024, 3, 1), BillReportRole.BUDGET_DEBATE
    )

    with pytest.raises(HansardBillKeyError, match="Bill 7 has no READING report"):
        get_bill_key(7, [budget_row])
    with pytest.raises(HansardBillKeyError, match="Bill 7 has no READING report"):
        get_bill_key(7, [])


def test_a_member_gets_one_row_per_report_with_the_count_the_first_ordinal_and_the_first_label() -> (
    None
):
    ordinal_label_rows = [
        SpeechOrdinalLabelRow(10, 5, 4, "Ms A (Bishan)"),
        SpeechOrdinalLabelRow(10, 6, 3, "Mr B"),
        SpeechOrdinalLabelRow(11, 5, 1, "Ms A"),
        SpeechOrdinalLabelRow(10, 5, 2, "Ms A"),
        SpeechOrdinalLabelRow(10, 5, 9, "Ms A"),
    ]

    bill_report_speakers = build_bill_report_speakers(
        ordinal_label_rows, {10: "r10", 11: "r11"}
    )

    assert [
        (
            bill_report_speaker.speech_count,
            bill_report_speaker.first_ordinal,
            bill_report_speaker.printed_speaker,
            bill_report_speaker.sprs_report_id,
            bill_report_speaker.speaker_id,
        )
        for bill_report_speaker in bill_report_speakers
    ] == [
        (3, 2, "Ms A", "r10", 5),
        (1, 3, "Mr B", "r10", 6),
        (1, 1, "Ms A", "r11", 5),
    ]


def test_no_rows_give_no_member_rows() -> None:
    assert build_bill_report_speakers([], {}) == []


def test_stage_lines_copy_the_ordinal_the_text_and_the_report() -> None:
    ordinal_transcript_rows = [
        SpeechOrdinalTranscriptRow(10, 3, "Bill read a Third time and passed."),
        SpeechOrdinalTranscriptRow(11, 1, "Bill read a Third time and passed."),
    ]

    bill_stage_lines = build_bill_stage_lines(
        BillStage.THIRD_READING, ordinal_transcript_rows, {10: "r10", 11: "r11"}
    )

    assert [
        (
            bill_stage_line.stage,
            bill_stage_line.printed_text,
            bill_stage_line.ordinal,
            bill_stage_line.sprs_report_id,
        )
        for bill_stage_line in bill_stage_lines
    ] == [
        (BillStage.THIRD_READING, "Bill read a Third time and passed.", 3, "r10"),
        (BillStage.THIRD_READING, "Bill read a Third time and passed.", 1, "r11"),
    ]
