from datetime import datetime

from crud.report import ReportSittingDateTitleRow
from services.bill import BillGrouping, group_bills
from utils.title_key import get_title_key


def _report_row(
    report_id: int, sitting_date: datetime, title: str
) -> ReportSittingDateTitleRow:
    return ReportSittingDateTitleRow(report_id, sitting_date, title)


def _group(
    report_rows: list[ReportSittingDateTitleRow],
    third_reading_report_ids: set[int],
    first_reading_report_ids: frozenset[int] = frozenset(),
) -> BillGrouping:
    return group_bills(
        report_rows, first_reading_report_ids, frozenset(third_reading_report_ids)
    )


def test_title_key_keeps_lower_case_letters_and_digits_only() -> None:
    assert get_title_key("Moneylenders (Amendment) Bill") == "moneylendersamendmentbill"
    assert get_title_key("(AMENDMENT)BILL") == "amendmentbill"
    assert get_title_key("Road Traffic (No. 2) Bill") == "roadtrafficno2bill"


def test_two_same_title_bills_passed_four_months_apart_stay_two_bills() -> None:
    grouping = _group(
        [
            _report_row(1, datetime(2005, 10, 17), "MONEYLENDERS (AMENDMENT) BILL"),
            _report_row(2, datetime(2006, 2, 20), "MONEYLENDERS (AMENDMENT) BILL"),
        ],
        {1, 2},
    )

    assert [
        (bill_group.report_ids, bill_group.is_passed)
        for bill_group in grouping.bill_groups
    ] == [([1], True), ([2], True)]


def test_a_first_reading_title_missing_a_space_joins_the_later_title() -> None:
    grouping = _group(
        [
            _report_row(1, datetime(1998, 5, 4), "CONTROL OF PLANTS (AMENDMENT)BILL"),
            _report_row(2, datetime(1998, 6, 29), "Control of Plants (Amendment) Bill"),
        ],
        {2},
    )

    (bill_group,) = grouping.bill_groups
    assert bill_group.report_ids == [1, 2]
    assert bill_group.title == "Control of Plants (Amendment) Bill"
    assert bill_group.title_key == "controlofplantsamendmentbill"
    assert bill_group.first_sitting_date == datetime(1998, 5, 4)
    assert bill_group.last_sitting_date == datetime(1998, 6, 29)
    assert bill_group.is_passed


def test_a_second_reading_split_over_two_days_is_one_bill() -> None:
    grouping = _group(
        [
            _report_row(
                1, datetime(2026, 3, 10), "Land Transport and Related Matters Bill"
            ),
            _report_row(
                2, datetime(2026, 3, 11), "Land Transport and Related Matters Bill"
            ),
        ],
        {2},
    )

    (bill_group,) = grouping.bill_groups
    assert bill_group.report_ids == [1, 2]
    assert bill_group.is_passed


def test_a_no_2_sequel_is_a_separate_bill() -> None:
    grouping = _group(
        [
            _report_row(
                1, datetime(2026, 3, 10), "Land Transport and Related Matters Bill"
            ),
            _report_row(
                2,
                datetime(2026, 9, 8),
                "Land Transport and Related Matters (No 2) Bill",
            ),
        ],
        {1},
    )

    assert [
        (bill_group.title_key, bill_group.report_ids)
        for bill_group in grouping.bill_groups
    ] == [
        ("landtransportandrelatedmattersbill", [1]),
        ("landtransportandrelatedmattersno2bill", [2]),
    ]


def test_a_bill_introduced_in_december_and_passed_next_year_is_one_bill() -> None:
    grouping = _group(
        [
            _report_row(1, datetime(2024, 12, 2), "Workplace Safety Bill"),
            _report_row(2, datetime(2025, 1, 15), "Workplace Safety Bill"),
        ],
        {2},
    )

    (bill_group,) = grouping.bill_groups
    assert bill_group.report_ids == [1, 2]
    assert bill_group.is_passed


def test_a_gap_of_366_days_keeps_the_bill_and_367_days_starts_a_new_one() -> None:
    kept_grouping = _group(
        [
            _report_row(1, datetime(2000, 1, 1), "Select Committee Bill"),
            _report_row(2, datetime(2001, 1, 1), "Select Committee Bill"),
        ],
        {2},
    )
    split_grouping = _group(
        [
            _report_row(1, datetime(2000, 1, 1), "Select Committee Bill"),
            _report_row(2, datetime(2001, 1, 2), "Select Committee Bill"),
        ],
        {2},
    )

    assert [bill_group.report_ids for bill_group in kept_grouping.bill_groups] == [
        [1, 2]
    ]
    assert [
        (bill_group.report_ids, bill_group.is_passed)
        for bill_group in split_grouping.bill_groups
    ] == [([1], False), ([2], True)]


def test_a_report_on_the_day_a_bill_passes_joins_it() -> None:
    grouping = _group(
        [
            _report_row(1, datetime(2010, 4, 5), "Estate Duty Bill"),
            _report_row(2, datetime(2010, 4, 5), "Estate Duty Bill"),
            _report_row(3, datetime(2010, 4, 6), "Estate Duty Bill"),
        ],
        {1},
    )

    assert [
        (bill_group.report_ids, bill_group.is_passed)
        for bill_group in grouping.bill_groups
    ] == [([1, 2], True), ([3], False)]


def test_titles_that_name_no_bill_are_skipped_and_counted() -> None:
    grouping = _group(
        [
            _report_row(1, datetime(2010, 4, 5), "ADJOURNMENT"),
            _report_row(2, datetime(2010, 4, 5), "BILLS INTRODUCED"),
            _report_row(3, datetime(2010, 4, 5), "Estate Duty Bill"),
            _report_row(4, datetime(2010, 4, 6), "EXEMPTED BUSINESS"),
        ],
        set(),
    )

    assert [
        (report_row.id, report_row.title) for report_row in grouping.skipped_report_rows
    ] == [(1, "ADJOURNMENT"), (2, "BILLS INTRODUCED"), (4, "EXEMPTED BUSINESS")]
    assert [bill_group.report_ids for bill_group in grouping.bill_groups] == [[3]]


def test_bills_come_back_in_order_of_first_report() -> None:
    grouping = _group(
        [
            _report_row(1, datetime(2010, 4, 5), "Alpha Bill"),
            _report_row(2, datetime(2010, 4, 6), "Beta Bill"),
            _report_row(3, datetime(2010, 4, 7), "Alpha Bill"),
        ],
        set(),
    )

    assert [bill_group.title for bill_group in grouping.bill_groups] == [
        "Alpha Bill",
        "Beta Bill",
    ]


def test_a_bill_read_a_first_time_again_after_it_lapsed_starts_a_new_bill() -> None:
    grouping = _group(
        [
            _report_row(42552, datetime(1990, 11, 9), "ARCHITECTS BILL"),
            _report_row(30052, datetime(1990, 12, 20), "ARCHITECTS BILL"),
            _report_row(30001, datetime(1991, 2, 26), "ARCHITECTS BILL"),
            _report_row(29914, datetime(1991, 3, 22), "ARCHITECTS BILL"),
            _report_row(29859, datetime(1991, 6, 28), "ARCHITECTS BILL"),
        ],
        {29859},
        frozenset({42552, 30001}),
    )

    assert [
        (bill_group.report_ids, bill_group.is_passed)
        for bill_group in grouping.bill_groups
    ] == [([42552, 30052], False), ([30001, 29914, 29859], True)]


def test_a_reintroduction_inside_one_year_of_the_lapsed_bill_is_a_new_bill() -> None:
    grouping = _group(
        [
            _report_row(32061, datetime(1986, 1, 10), "SECURITIES INDUSTRY BILL"),
            _report_row(32030, datetime(1986, 2, 26), "SECURITIES INDUSTRY BILL"),
            _report_row(31804, datetime(1986, 3, 31), "SECURITIES INDUSTRY BILL"),
        ],
        {31804},
        frozenset({32061, 32030}),
    )

    assert [bill_group.report_ids for bill_group in grouping.bill_groups] == [
        [32061],
        [32030, 31804],
    ]


def test_two_first_readings_on_one_sitting_date_stay_one_bill() -> None:
    grouping = _group(
        [
            _report_row(1, datetime(1991, 2, 26), "Estate Duty Bill"),
            _report_row(2, datetime(1991, 2, 26), "Estate Duty Bill"),
        ],
        set(),
        frozenset({1, 2}),
    )

    assert [bill_group.report_ids for bill_group in grouping.bill_groups] == [[1, 2]]


def test_a_report_with_no_first_reading_joins_the_open_bill() -> None:
    grouping = _group(
        [
            _report_row(1, datetime(1991, 2, 26), "Estate Duty Bill"),
            _report_row(2, datetime(1991, 3, 22), "Estate Duty Bill"),
        ],
        set(),
        frozenset({1}),
    )

    assert [bill_group.report_ids for bill_group in grouping.bill_groups] == [[1, 2]]
