from datetime import date

from crud.attendance import AttendanceSittingDateRow
from services.sitting_span import SittingSpanRecord, build_sitting_span_records

_SPEAKER_ID = 7
_OTHER_SPEAKER_ID = 8


def test_build_sitting_span_records_gives_the_bounds_and_count_of_three_sittings() -> (
    None
):
    attendance_sitting_date_rows = [
        AttendanceSittingDateRow(_SPEAKER_ID, "10-3-1964"),
        AttendanceSittingDateRow(_SPEAKER_ID, "22-10-1963"),
        AttendanceSittingDateRow(_SPEAKER_ID, "24-1-1968"),
    ]

    assert build_sitting_span_records(attendance_sitting_date_rows) == [
        SittingSpanRecord(date(1963, 10, 22), date(1968, 1, 24), 3, _SPEAKER_ID)
    ]


def test_build_sitting_span_records_counts_a_repeated_sitting_date_once() -> None:
    attendance_sitting_date_rows = [
        AttendanceSittingDateRow(_SPEAKER_ID, "2-1-2020"),
        AttendanceSittingDateRow(_SPEAKER_ID, "2-1-2020"),
    ]

    records = build_sitting_span_records(attendance_sitting_date_rows)

    assert [record.sitting_count for record in records] == [1]


def test_build_sitting_span_records_gives_a_single_sitting_the_same_first_and_last_date() -> (
    None
):
    attendance_sitting_date_rows = [AttendanceSittingDateRow(_SPEAKER_ID, "2-1-2020")]

    assert build_sitting_span_records(attendance_sitting_date_rows) == [
        SittingSpanRecord(date(2020, 1, 2), date(2020, 1, 2), 1, _SPEAKER_ID)
    ]


def test_build_sitting_span_records_keeps_each_speaker_apart_and_sorts_by_speaker() -> (
    None
):
    attendance_sitting_date_rows = [
        AttendanceSittingDateRow(_OTHER_SPEAKER_ID, "5-3-2020"),
        AttendanceSittingDateRow(_SPEAKER_ID, "2-1-2020"),
        AttendanceSittingDateRow(_OTHER_SPEAKER_ID, "9-3-2020"),
    ]

    assert build_sitting_span_records(attendance_sitting_date_rows) == [
        SittingSpanRecord(date(2020, 1, 2), date(2020, 1, 2), 1, _SPEAKER_ID),
        SittingSpanRecord(date(2020, 3, 5), date(2020, 3, 9), 2, _OTHER_SPEAKER_ID),
    ]


def test_build_sitting_span_records_returns_nothing_for_no_rows() -> None:
    assert build_sitting_span_records([]) == []
