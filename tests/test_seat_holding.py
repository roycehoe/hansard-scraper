from datetime import date

import pytest

from crud.attendance import AttendanceSeatRow
from services.seat_holding import (
    SeatHoldingRecord,
    build_seat_holding_records,
    get_division_key,
)

_SPEAKER_ID = 7
_OTHER_SPEAKER_ID = 8


@pytest.mark.parametrize(
    ("location_name", "division_key"),
    [
        ("Aljunied GRC", "aljunied"),
        ("West Coast-Jurong West", "west coast jurong west"),
        ("Bishan - Toa Payoh", "bishan toa payoh"),
        ("Holland-Bukit Timah GRC", "holland bukit timah"),
        (" Radin Mas SMC", "radin mas"),
    ],
)
def test_get_division_key_folds_separators_suffix_and_case(
    location_name: str, division_key: str
) -> None:
    assert get_division_key(location_name) == division_key


@pytest.mark.parametrize(
    "location_name",
    [
        "Nominated Member",
        "Nominated",
        "Non-Constituency Member",
        "ex-officio",
        "Acting",
    ],
)
def test_build_seat_holding_records_leaves_out_a_label_that_is_not_a_division(
    location_name: str,
) -> None:
    attendance_seat_rows = [AttendanceSeatRow(_SPEAKER_ID, location_name, "2-1-2020")]

    assert build_seat_holding_records(attendance_seat_rows) == []


def test_build_seat_holding_records_gives_the_bounds_and_count_of_two_sittings() -> (
    None
):
    attendance_seat_rows = [
        AttendanceSeatRow(_SPEAKER_ID, "Aljunied GRC", "10-3-2021"),
        AttendanceSeatRow(_SPEAKER_ID, "Aljunied GRC", "2-1-2020"),
    ]

    assert build_seat_holding_records(attendance_seat_rows) == [
        SeatHoldingRecord(
            "aljunied", "Aljunied GRC", date(2020, 1, 2), date(2021, 3, 10), 2, 7
        )
    ]


def test_build_seat_holding_records_counts_a_repeated_sitting_date_once() -> None:
    attendance_seat_rows = [
        AttendanceSeatRow(_SPEAKER_ID, "Aljunied GRC", "2-1-2020"),
        AttendanceSeatRow(_SPEAKER_ID, "Aljunied GRC", "2-1-2020"),
    ]

    records = build_seat_holding_records(attendance_seat_rows)

    assert [record.sitting_count for record in records] == [1]


def test_build_seat_holding_records_merges_two_labels_that_fold_together() -> None:
    attendance_seat_rows = [
        AttendanceSeatRow(_SPEAKER_ID, "Aljunied", "10-3-2021"),
        AttendanceSeatRow(_SPEAKER_ID, "Aljunied GRC", "2-1-2020"),
    ]

    assert build_seat_holding_records(attendance_seat_rows) == [
        SeatHoldingRecord(
            "aljunied", "Aljunied GRC", date(2020, 1, 2), date(2021, 3, 10), 2, 7
        )
    ]


def test_build_seat_holding_records_keeps_the_smaller_label_on_a_date_tie() -> None:
    attendance_seat_rows = [
        AttendanceSeatRow(_SPEAKER_ID, "Aljunied GRC", "2-1-2020"),
        AttendanceSeatRow(_SPEAKER_ID, "Aljunied", "2-1-2020"),
    ]

    records = build_seat_holding_records(attendance_seat_rows)

    assert [record.location_name for record in records] == ["Aljunied"]


def test_build_seat_holding_records_sorts_by_speaker_then_division() -> None:
    attendance_seat_rows = [
        AttendanceSeatRow(_OTHER_SPEAKER_ID, "Bishan-Toa Payoh GRC", "2-1-2020"),
        AttendanceSeatRow(_SPEAKER_ID, "Tampines GRC", "2-1-2020"),
        AttendanceSeatRow(_SPEAKER_ID, "Aljunied GRC", "2-1-2020"),
    ]

    records = build_seat_holding_records(attendance_seat_rows)

    assert [(record.speaker_id, record.division_key) for record in records] == [
        (_SPEAKER_ID, "aljunied"),
        (_SPEAKER_ID, "tampines"),
        (_OTHER_SPEAKER_ID, "bishan toa payoh"),
    ]
