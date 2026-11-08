from datetime import datetime

import pytest

from crud.report import ReportSittingDateTitleRow
from exceptions import HansardHandKeptEntryError
from schemas.bill_title_correction import BillTitleCorrection
from schemas.hand_kept_bill import HandKeptBill
from services.bill import BillGrouping, group_bills, is_other_type_bill_reading
from utils.title_key import get_title_key


def _report_row(
    report_id: int, sitting_date: datetime, title: str
) -> ReportSittingDateTitleRow:
    return ReportSittingDateTitleRow(report_id, sitting_date, title)


def _group(
    report_rows: list[ReportSittingDateTitleRow],
    third_reading_report_ids: set[int],
    first_reading_report_ids: frozenset[int] = frozenset(),
    title_corrections: list[BillTitleCorrection] = [],
    hand_kept_bills: list[HandKeptBill] = [],
    hand_kept_report_rows: list[ReportSittingDateTitleRow] = [],
) -> BillGrouping:
    return group_bills(
        report_rows,
        first_reading_report_ids,
        frozenset(third_reading_report_ids),
        title_corrections,
        hand_kept_bills,
        hand_kept_report_rows or report_rows,
        [],
        [],
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


def _correction(
    report_id: int, printed_title: str, corrected_title: str
) -> BillTitleCorrection:
    return BillTitleCorrection(
        report_id=report_id,
        printed_title=printed_title,
        corrected_title=corrected_title,
        reason="A reason.",
    )


def test_a_corrected_first_reading_title_joins_its_siblings_and_gives_the_title() -> (
    None
):
    grouping = _group(
        [
            _report_row(
                1, datetime(2019, 10, 7), "Good and Services Tax (Amendment) Bill"
            ),
            _report_row(
                2, datetime(2019, 11, 4), "Goods and Services Tax (Amendment) Bill"
            ),
        ],
        {2},
        title_corrections=[
            _correction(
                1,
                "Good and Services Tax (Amendment) Bill",
                "Goods and Services Tax (Amendment) Bill",
            )
        ],
    )

    (bill_group,) = grouping.bill_groups
    assert bill_group.report_ids == [1, 2]
    assert bill_group.title == "Goods and Services Tax (Amendment) Bill"
    assert bill_group.first_sitting_date == datetime(2019, 10, 7)


def test_a_correction_whose_printed_title_differs_from_the_report_raises() -> None:
    with pytest.raises(HansardHandKeptEntryError, match="report 1 prints"):
        _group(
            [_report_row(1, datetime(2019, 10, 7), "Tax Bill")],
            set(),
            title_corrections=[_correction(1, "Taxes Bill", "Tax Bill")],
        )


def test_a_correction_for_a_report_that_is_not_a_bill_report_raises() -> None:
    with pytest.raises(HansardHandKeptEntryError, match="report 9 is not"):
        _group(
            [_report_row(1, datetime(2019, 10, 7), "Tax Bill")],
            set(),
            title_corrections=[_correction(9, "Tax Bill", "Taxes Bill")],
        )


def _hand_kept_bill(title: str, report_ids: list[int]) -> HandKeptBill:
    return HandKeptBill(title=title, report_ids=report_ids, reason="A reason.")


def test_a_hand_kept_bill_replaces_the_rule_built_bills_of_a_renamed_bill() -> None:
    grouping = _group(
        [
            _report_row(
                3,
                datetime(2004, 10, 19),
                "BUILDING MAINTENANCE AND STRATA MANAGEMENT BILL",
            ),
            _report_row(
                1, datetime(2004, 2, 6), "BUILDING MAINTENANCE AND MANAGEMENT BILL"
            ),
            _report_row(
                2, datetime(2004, 4, 19), "BUILDING MAINTENANCE AND MANAGEMENT BILL"
            ),
            _report_row(4, datetime(2004, 5, 1), "MONEYLENDERS BILL"),
        ],
        {3},
        hand_kept_bills=[
            _hand_kept_bill(
                "BUILDING MAINTENANCE AND STRATA MANAGEMENT BILL", [3, 1, 2]
            )
        ],
    )

    assert [
        (bill_group.title_key, bill_group.report_ids, bill_group.is_passed)
        for bill_group in grouping.bill_groups
    ] == [
        ("buildingmaintenanceandstratamanagementbill", [1, 2, 3], True),
        ("moneylendersbill", [4], False),
    ]
    assert grouping.bill_groups[0].first_sitting_date == datetime(2004, 2, 6)
    assert grouping.bill_groups[0].last_sitting_date == datetime(2004, 10, 19)


def test_a_hand_kept_bill_joins_a_report_that_is_not_a_bill_report() -> None:
    motion_row = _report_row(
        9, datetime(1960, 11, 16), "ADJOURNMENT TO A LATER DAY MOTION"
    )

    grouping = _group(
        [_report_row(1, datetime(1960, 5, 1), "MONEYLENDERS BILL")],
        set(),
        hand_kept_bills=[
            _hand_kept_bill(
                "CRIMINAL LAW (TEMPORARY PROVISIONS) (AMENDMENT NO. 2) BILL", [9]
            )
        ],
        hand_kept_report_rows=[motion_row],
    )

    assert [bill_group.report_ids for bill_group in grouping.bill_groups] == [[1], [9]]
    assert (
        grouping.bill_groups[1].title_key
        == "criminallawtemporaryprovisionsamendmentno2bill"
    )


def test_a_hand_kept_bill_takes_its_report_out_of_the_skipped_reports() -> None:
    grouping = _group(
        [_report_row(1, datetime(1960, 11, 16), "ADJOURNMENT")],
        set(),
        hand_kept_bills=[_hand_kept_bill("ESTATE BILL", [1])],
    )

    assert grouping.skipped_report_rows == []
    assert [bill_group.report_ids for bill_group in grouping.bill_groups] == [[1]]


def test_a_hand_kept_bill_that_splits_a_rule_built_bill_raises() -> None:
    with pytest.raises(HansardHandKeptEntryError, match="splits the bill"):
        _group(
            [
                _report_row(1, datetime(2004, 2, 6), "ESTATE BILL"),
                _report_row(2, datetime(2004, 4, 19), "ESTATE BILL"),
            ],
            set(),
            hand_kept_bills=[_hand_kept_bill("ESTATE BILL", [1])],
        )


def test_a_hand_kept_bill_listing_a_report_that_is_not_stored_raises() -> None:
    with pytest.raises(
        HansardHandKeptEntryError, match="report 7, which is not stored"
    ):
        _group(
            [_report_row(1, datetime(2004, 2, 6), "ESTATE BILL")],
            set(),
            hand_kept_bills=[_hand_kept_bill("ESTATE BILL", [1, 7])],
        )


@pytest.mark.parametrize(
    ("title", "is_first_reading", "is_second_reading", "is_third_reading", "expected"),
    [
        ("INSURANCE (AMENDMENT) BILL", True, False, False, True),
        ("TRADE (AMENDMENT) BILL, 1960", False, True, False, True),
        ("TRADE (AMENDMENT) BILL", False, False, True, True),
        ("COPYRIGHT BILL", False, False, False, False),
        ("SELECT COMMITTEE ON THE TRADE BILL", False, False, False, False),
        (
            "Impact of Amendments to Maintenance of Parents Bill Act",
            True,
            True,
            True,
            False,
        ),
        ("Bills of Exchange", True, True, True, False),
    ],
)
def test_another_type_joins_the_grouping_when_its_title_ends_in_bill_and_it_holds_a_reading(
    title: str,
    is_first_reading: bool,
    is_second_reading: bool,
    is_third_reading: bool,
    expected: bool,
) -> None:
    assert (
        is_other_type_bill_reading(
            title, is_first_reading, is_second_reading, is_third_reading
        )
        is expected
    )
