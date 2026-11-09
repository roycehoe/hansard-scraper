import json
from datetime import date
from typing import Optional

import pytest

from enums import LeaveEntryFormat, LeaveNameSource, LeaveYearSource
from services.leave_period import build_leave_entries_from_list
from utils.leave_entry import (
    DayAndMonth,
    LeaveDates,
    get_candidate_years,
    get_leave_period_key,
    get_nearest_year_dates,
    is_covering_sitting,
)

_HEADING_YEAR = "2020"


def _build_permission_list(*entries: dict) -> str:
    return json.dumps(list(entries))


def _build_entry(
    mp_name: Optional[str],
    printed_from: Optional[str],
    printed_to: Optional[str],
    end_dt_flag: bool = False,
    end_dt_text: Optional[str] = None,
) -> dict:
    return {
        "mpName": mp_name,
        "from": printed_from,
        "to": printed_to,
        "endDtFlag": end_dt_flag,
        "endDtText": end_dt_text,
    }


def test_a_normal_entry_reads_its_name_and_dates() -> None:
    permission_list = _build_permission_list(_build_entry("Mr Lee", "5 Mar", "7 Mar"))

    leave_entries = build_leave_entries_from_list(
        permission_list, _HEADING_YEAR, _HEADING_YEAR, date(2020, 3, 6)
    )

    assert len(leave_entries) == 1
    leave_entry = leave_entries[0]
    assert leave_entry.ordinal == 1
    assert leave_entry.printed_name == "Mr Lee"
    assert leave_entry.carried_name is None
    assert leave_entry.leave_dates == LeaveDates(date(2020, 3, 5), date(2020, 3, 7))
    assert leave_entry.printed_from == "5 Mar"
    assert leave_entry.printed_to == "7 Mar"
    assert leave_entry.printed_heading_from == _HEADING_YEAR
    assert leave_entry.printed_line is None
    assert leave_entry.office_printed is None
    assert leave_entry.entry_format == LeaveEntryFormat.STRUCTURED_LIST
    assert leave_entry.name_source == LeaveNameSource.PRINTED
    assert leave_entry.year_source == LeaveYearSource.NEAREST_TO_SITTING


@pytest.mark.parametrize("blank_name", [None, "", "  "])
def test_a_blank_name_carries_the_row_above(blank_name: Optional[str]) -> None:
    permission_list = _build_permission_list(
        _build_entry("Mr Lee", "5 Mar", "7 Mar"),
        _build_entry(blank_name, "8 Mar", "9 Mar"),
    )

    leave_entries = build_leave_entries_from_list(
        permission_list, None, None, date(2020, 3, 6)
    )

    assert leave_entries[1].printed_name is None
    assert leave_entries[1].carried_name == "Mr Lee"
    assert leave_entries[1].name_source == LeaveNameSource.CARRIED_FROM_ROW_ABOVE


def test_a_blank_first_row_has_no_name() -> None:
    permission_list = _build_permission_list(_build_entry(None, "5 Mar", "7 Mar"))

    leave_entries = build_leave_entries_from_list(
        permission_list, None, None, date(2020, 3, 6)
    )

    assert leave_entries[0].printed_name is None
    assert leave_entries[0].carried_name is None
    assert leave_entries[0].name_source == LeaveNameSource.NONE


def test_a_range_over_new_year_reads_the_year_before() -> None:
    permission_list = _build_permission_list(_build_entry("Mr Lee", "28 Dec", "3 Jan"))

    leave_entries = build_leave_entries_from_list(
        permission_list, None, None, date(2020, 1, 10)
    )

    assert leave_entries[0].leave_dates == LeaveDates(
        date(2019, 12, 28), date(2020, 1, 3)
    )


def test_till_further_notice_stores_to_and_the_text_and_reads_no_end_date() -> None:
    permission_list = _build_permission_list(
        _build_entry(
            "Mr Lee", "5 Mar", "Till further notice", True, "Till further notice"
        )
    )

    leave_entries = build_leave_entries_from_list(
        permission_list, None, None, date(2020, 3, 6)
    )

    assert leave_entries[0].leave_dates == LeaveDates(date(2020, 3, 5), None)
    assert leave_entries[0].printed_to == "Till further notice"
    assert leave_entries[0].end_text == "Till further notice"


@pytest.mark.parametrize(
    ("printed_from", "sitting_date", "expected_start_date", "is_expected_covering"),
    [
        ("12 Aug", date(2024, 2, 12), date(2023, 8, 12), True),
        ("20 Nov", date(2024, 10, 20), date(2024, 11, 20), False),
        ("20 Nov", date(2024, 10, 19), date(2023, 11, 20), True),
    ],
)
def test_an_open_period_takes_no_year_more_than_31_days_after_the_sitting(
    printed_from: str,
    sitting_date: date,
    expected_start_date: date,
    is_expected_covering: bool,
) -> None:
    permission_list = _build_permission_list(
        _build_entry("Mr Lee", printed_from, "16 Jan", True, "Till further notice")
    )

    leave_entries = build_leave_entries_from_list(
        permission_list, None, None, sitting_date
    )

    assert leave_entries[0].leave_dates == LeaveDates(expected_start_date, None)
    assert (
        is_covering_sitting(expected_start_date, None, sitting_date)
        is is_expected_covering
    )


def test_29_february_reads_in_a_leap_year() -> None:
    permission_list = _build_permission_list(_build_entry("Mr Lee", "29 Feb", "1 Mar"))

    leave_entries = build_leave_entries_from_list(
        permission_list, None, None, date(2020, 3, 1)
    )

    assert leave_entries[0].leave_dates == LeaveDates(
        date(2020, 2, 29), date(2020, 3, 1)
    )


def test_29_february_with_no_leap_year_among_the_candidates_stores_no_dates() -> None:
    permission_list = _build_permission_list(_build_entry("Mr Lee", "29 Feb", "1 Mar"))

    leave_entries = build_leave_entries_from_list(
        permission_list, None, None, date(2022, 3, 1)
    )

    assert leave_entries[0].leave_dates is None
    assert leave_entries[0].year_source is None


def test_a_range_nearest_to_the_sitting_reads_the_year_before_the_heading() -> None:
    permission_list = _build_permission_list(_build_entry("Mr Lee", "16 Nov", "17 Nov"))

    leave_entries = build_leave_entries_from_list(
        permission_list, "2017", "2017", date(2017, 1, 9)
    )

    assert leave_entries[0].leave_dates == LeaveDates(
        date(2016, 11, 16), date(2016, 11, 17)
    )
    assert leave_entries[0].printed_heading_from == "2017"


def test_a_tie_between_two_years_stores_no_dates() -> None:
    nearest_year_dates = get_nearest_year_dates(
        DayAndMonth(2, 7), None, date(2021, 7, 2), [2020, 2022]
    )

    assert nearest_year_dates is None


def test_an_unreadable_date_stores_no_dates() -> None:
    permission_list = _build_permission_list(_build_entry("Mr Lee", "soon", "7 Mar"))

    leave_entries = build_leave_entries_from_list(
        permission_list, None, None, date(2020, 3, 6)
    )

    assert leave_entries[0].leave_dates is None
    assert leave_entries[0].printed_from == "soon"


def test_get_candidate_years_gives_the_year_either_side() -> None:
    assert get_candidate_years(date(2020, 6, 1)) == [2019, 2020, 2021]


def test_get_leave_period_key_for_a_named_row() -> None:
    period_key = get_leave_period_key(
        "  Mr   LEE ", date(2020, 3, 5), date(2020, 3, 7), 1, 1
    )

    assert period_key == "mr lee|2020-03-05|2020-03-07"


def test_get_leave_period_key_for_an_open_row() -> None:
    period_key = get_leave_period_key("Mr Lee", date(2020, 3, 5), None, 1, 1)

    assert period_key == "mr lee|2020-03-05|open"


def test_get_leave_period_key_for_a_row_with_no_name_is_unmerged() -> None:
    period_key = get_leave_period_key(None, date(2020, 3, 5), None, 12, 3)

    assert period_key == "entry|12|3"


def test_get_leave_period_key_for_a_row_with_no_dates_is_unmerged() -> None:
    period_key = get_leave_period_key("Mr Lee", None, None, 12, 4)

    assert period_key == "entry|12|4"


@pytest.mark.parametrize(
    ("start_date", "end_date", "sitting_date", "expected"),
    [
        (date(2020, 3, 5), date(2020, 3, 7), date(2020, 3, 6), True),
        (date(2020, 3, 5), date(2020, 3, 7), date(2020, 3, 8), False),
        (date(2020, 3, 5), None, date(2020, 3, 8), True),
        (date(2020, 3, 5), None, date(2020, 3, 4), False),
        (None, None, date(2020, 3, 4), None),
    ],
)
def test_is_covering_sitting(
    start_date: Optional[date],
    end_date: Optional[date],
    sitting_date: date,
    expected: Optional[bool],
) -> None:
    assert is_covering_sitting(start_date, end_date, sitting_date) is expected
