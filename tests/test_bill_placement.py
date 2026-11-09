from datetime import datetime
from typing import Optional

import pytest

import services.bill as bill_service
from crud.bill import BillRow
from crud.report import ReportPlacementRow, ReportSittingDateTitleRow
from enums import BillLeftOutReason
from services.bill import BillPlacement, group_bills, place_bill_reports
from utils.title_key import get_title_key

_TITLE = "Estate Duty Bill"
_STORED_BILL_ID = 7
_TWO_REPORTS = 2
_TWO_BILLS = 2
_DAYS_TO_JOIN = 366
_DAYS_TO_START = 367


def _report_row(
    report_id: int, sprs_report_id: str, sitting_date: datetime, title: str
) -> ReportPlacementRow:
    return ReportPlacementRow(report_id, sprs_report_id, sitting_date, title, "bill")


def _stored_bill_row(
    bill_id: int,
    title: str,
    first_sitting_date: datetime,
    last_sitting_date: datetime,
    is_passed: bool,
) -> BillRow:
    return BillRow(
        bill_id,
        title,
        get_title_key(title),
        first_sitting_date,
        last_sitting_date,
        is_passed,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def _place(
    report_rows: list[ReportPlacementRow],
    stored_bill_rows: list[BillRow] = [],
    first_reading_report_ids: frozenset[int] = frozenset(),
    third_reading_report_ids: frozenset[int] = frozenset(),
    bill_id_to_bill_key: dict[int, str] = {},
) -> BillPlacement:
    return place_bill_reports(
        report_rows,
        first_reading_report_ids,
        third_reading_report_ids,
        stored_bill_rows,
        bill_id_to_bill_key,
    )


def test_a_report_with_no_stored_bill_starts_a_new_bill() -> None:
    report_row = _report_row(1, "estate-1", datetime(2025, 1, 15), _TITLE)

    placement = _place([report_row])

    assert len(placement.placed_bills) == 1
    placed_bill = placement.placed_bills[0]
    assert placed_bill.bill_id is None
    assert placed_bill.title_key == "estatedutybill"
    assert placed_bill.first_sitting_date == report_row.sitting_date
    assert placed_bill.last_sitting_date == report_row.sitting_date
    assert not placed_bill.is_passed
    assert placed_bill.report_rows == [report_row]
    assert placement.left_out_reports == []


def test_two_reports_of_one_new_bill_in_one_call_make_one_bill() -> None:
    first_row = _report_row(1, "estate-1", datetime(2025, 1, 15), _TITLE)
    second_row = _report_row(2, "estate-2", datetime(2025, 2, 19), _TITLE)

    placement = _place(
        [first_row, second_row],
        first_reading_report_ids=frozenset({1}),
        third_reading_report_ids=frozenset({2}),
    )

    assert len(placement.placed_bills) == 1
    placed_bill = placement.placed_bills[0]
    assert [report_row.id for report_row in placed_bill.report_rows] == [1, 2]
    assert placed_bill.first_sitting_date == first_row.sitting_date
    assert placed_bill.last_sitting_date == second_row.sitting_date
    assert placed_bill.is_passed


def test_reports_are_placed_in_sitting_date_then_id_order_whatever_the_input_order() -> (
    None
):
    first_row = _report_row(1, "estate-1", datetime(2025, 1, 15), _TITLE)
    second_row = _report_row(2, "estate-2", datetime(2025, 2, 19), _TITLE)

    placement = _place(
        [second_row, first_row],
        first_reading_report_ids=frozenset({1}),
        third_reading_report_ids=frozenset({2}),
    )

    assert len(placement.placed_bills) == 1
    placed_bill = placement.placed_bills[0]
    assert [report_row.id for report_row in placed_bill.report_rows] == [1, 2]
    assert placed_bill.first_sitting_date == first_row.sitting_date
    assert placed_bill.last_sitting_date == second_row.sitting_date
    assert placed_bill.is_passed


def test_a_report_joins_the_one_open_stored_bill() -> None:
    stored_bill_row = _stored_bill_row(
        _STORED_BILL_ID, _TITLE, datetime(2025, 1, 15), datetime(2025, 1, 15), False
    )
    report_row = _report_row(2, "estate-2", datetime(2025, 2, 19), "ESTATE DUTY (BILL)")

    placement = _place(
        [report_row],
        [stored_bill_row],
        third_reading_report_ids=frozenset({2}),
    )

    assert len(placement.placed_bills) == 1
    placed_bill = placement.placed_bills[0]
    assert placed_bill.bill_id == _STORED_BILL_ID
    assert placed_bill.title == "ESTATE DUTY (BILL)"
    assert placed_bill.first_sitting_date == datetime(2025, 1, 15)
    assert placed_bill.last_sitting_date == report_row.sitting_date
    assert placed_bill.is_passed


def test_a_report_repeating_a_passed_bills_title_starts_a_new_bill() -> None:
    stored_bill_row = _stored_bill_row(
        _STORED_BILL_ID, _TITLE, datetime(2025, 1, 15), datetime(2025, 2, 19), True
    )
    report_row = _report_row(3, "estate-3", datetime(2025, 3, 5), _TITLE)

    placement = _place([report_row], [stored_bill_row])

    assert len(placement.placed_bills) == 1
    assert placement.placed_bills[0].bill_id is None


@pytest.mark.parametrize(
    ("days_later", "expected_bill_id"),
    [(_DAYS_TO_JOIN, _STORED_BILL_ID), (_DAYS_TO_START, None)],
)
def test_a_report_366_days_after_the_open_bill_joins_it_and_367_starts_a_new_bill(
    days_later: int, expected_bill_id: Optional[int]
) -> None:
    last_sitting_date = datetime(2024, 1, 1)
    stored_bill_row = _stored_bill_row(
        _STORED_BILL_ID, _TITLE, last_sitting_date, last_sitting_date, False
    )
    report_row = _report_row(
        3,
        "estate-3",
        datetime.fromordinal(last_sitting_date.toordinal() + days_later),
        _TITLE,
    )

    placement = _place([report_row], [stored_bill_row])

    assert len(placement.placed_bills) == 1
    assert placement.placed_bills[0].bill_id == expected_bill_id


def test_a_first_reading_after_an_unpassed_bill_starts_a_new_bill() -> None:
    stored_bill_row = _stored_bill_row(
        _STORED_BILL_ID, _TITLE, datetime(2025, 1, 15), datetime(2025, 1, 15), False
    )
    report_row = _report_row(3, "estate-3", datetime(2025, 3, 5), _TITLE)

    placement = _place(
        [report_row], [stored_bill_row], first_reading_report_ids=frozenset({3})
    )

    assert len(placement.placed_bills) == 1
    assert placement.placed_bills[0].bill_id is None


def test_a_bill_report_titled_adjournment_is_left_out() -> None:
    adjournment_row = _report_row(1, "adjourn-1", datetime(2025, 1, 15), "ADJOURNMENT")
    exempted_row = _report_row(
        2, "exempt-1", datetime(2025, 1, 15), "Exempted Business"
    )

    placement = _place([adjournment_row, exempted_row])

    assert placement.placed_bills == []
    assert len(placement.left_out_reports) == _TWO_REPORTS
    assert {left_out.reason for left_out in placement.left_out_reports} == {
        BillLeftOutReason.NO_BILL_WORD_IN_TITLE
    }


def test_a_report_dated_before_its_open_bills_last_sitting_is_left_out() -> None:
    stored_bill_row = _stored_bill_row(
        _STORED_BILL_ID, _TITLE, datetime(2025, 1, 15), datetime(2025, 3, 5), False
    )
    report_row = _report_row(3, "estate-3", datetime(2025, 2, 19), _TITLE)

    placement = _place([report_row], [stored_bill_row])

    assert placement.placed_bills == []
    assert [left_out.reason for left_out in placement.left_out_reports] == [
        BillLeftOutReason.DATED_BEFORE_OPEN_BILL
    ]


def test_a_title_key_whose_latest_date_two_stored_bills_share_leaves_the_report_out() -> (
    None
):
    shared_last_sitting_date = datetime(2025, 3, 5)
    stored_bill_rows = [
        _stored_bill_row(
            1, _TITLE, datetime(2025, 1, 15), shared_last_sitting_date, False
        ),
        _stored_bill_row(
            _TWO_BILLS, _TITLE, datetime(2025, 2, 19), shared_last_sitting_date, False
        ),
    ]
    report_row = _report_row(3, "estate-3", datetime(2025, 4, 9), _TITLE)

    placement = _place([report_row], stored_bill_rows)

    assert placement.placed_bills == []
    assert [left_out.reason for left_out in placement.left_out_reports] == [
        BillLeftOutReason.TWO_BILLS_SHARE_LATEST_DATE
    ]


def test_the_stored_bill_with_the_latest_date_is_the_open_one() -> None:
    stored_bill_rows = [
        _stored_bill_row(1, _TITLE, datetime(2024, 1, 15), datetime(2024, 2, 19), True),
        _stored_bill_row(
            _TWO_BILLS, _TITLE, datetime(2025, 1, 15), datetime(2025, 2, 19), False
        ),
    ]
    report_row = _report_row(3, "estate-3", datetime(2025, 3, 5), _TITLE)

    placement = _place([report_row], stored_bill_rows)

    assert len(placement.placed_bills) == 1
    assert placement.placed_bills[0].bill_id == _TWO_BILLS


def test_a_report_on_a_keyed_bills_first_date_with_a_lower_sprs_id_is_left_out() -> (
    None
):
    sitting_date = datetime(2025, 1, 15)
    stored_bill_row = _stored_bill_row(
        _STORED_BILL_ID, _TITLE, sitting_date, sitting_date, False
    )
    report_row = _report_row(3, "bill-a", sitting_date, _TITLE)

    placement = _place(
        [report_row], [stored_bill_row], bill_id_to_bill_key={_STORED_BILL_ID: "bill-b"}
    )

    assert placement.placed_bills == []
    assert [left_out.reason for left_out in placement.left_out_reports] == [
        BillLeftOutReason.SORTS_BELOW_STORED_KEY
    ]


def test_a_report_on_a_keyed_bills_first_date_with_a_higher_sprs_id_joins_it() -> None:
    sitting_date = datetime(2025, 1, 15)
    stored_bill_row = _stored_bill_row(
        _STORED_BILL_ID, _TITLE, sitting_date, sitting_date, False
    )
    report_row = _report_row(3, "bill-c", sitting_date, _TITLE)

    placement = _place(
        [report_row], [stored_bill_row], bill_id_to_bill_key={_STORED_BILL_ID: "bill-b"}
    )

    assert len(placement.placed_bills) == 1
    assert placement.placed_bills[0].bill_id == _STORED_BILL_ID
    assert placement.left_out_reports == []


def test_a_report_on_the_first_date_of_a_bill_with_no_key_row_joins_it() -> None:
    sitting_date = datetime(2025, 1, 15)
    stored_bill_row = _stored_bill_row(
        _STORED_BILL_ID, _TITLE, sitting_date, sitting_date, False
    )
    report_row = _report_row(3, "bill-a", sitting_date, _TITLE)

    placement = _place([report_row], [stored_bill_row], bill_id_to_bill_key={})

    assert len(placement.placed_bills) == 1
    assert placement.placed_bills[0].bill_id == _STORED_BILL_ID
    assert placement.left_out_reports == []


def test_the_key_rule_ignores_a_report_dated_after_the_bills_first_date() -> None:
    stored_bill_row = _stored_bill_row(
        _STORED_BILL_ID, _TITLE, datetime(2025, 1, 15), datetime(2025, 2, 19), False
    )
    report_row = _report_row(3, "bill-a", datetime(2025, 2, 19), _TITLE)

    placement = _place(
        [report_row], [stored_bill_row], bill_id_to_bill_key={_STORED_BILL_ID: "bill-b"}
    )

    assert len(placement.placed_bills) == 1
    assert placement.placed_bills[0].bill_id == _STORED_BILL_ID
    assert placement.left_out_reports == []


def test_placement_calls_the_shared_start_a_new_bill_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bill_service, "should_start_new_bill", lambda *arguments: True)
    report_rows = [
        _report_row(1, "estate-1", datetime(2025, 1, 15), _TITLE),
        _report_row(2, "estate-2", datetime(2025, 1, 16), _TITLE),
    ]

    placement = _place(report_rows)

    assert len(placement.placed_bills) == _TWO_BILLS


def test_batch_grouping_and_placement_make_the_same_bills() -> None:
    dated_titles = [
        (1, datetime(2020, 1, 10), "Alpha Bill"),
        (2, datetime(2020, 2, 10), "Alpha Bill"),
        (3, datetime(2021, 3, 15), "Alpha Bill"),
        (4, datetime(2020, 1, 10), "Beta Bill"),
        (5, datetime(2020, 3, 1), "Beta Bill"),
        (6, datetime(2020, 1, 10), "Gamma Bill"),
        (7, datetime(2020, 4, 19), "Gamma Bill"),
    ]
    first_reading_report_ids = frozenset({1, 4, 5})
    third_reading_report_ids = frozenset({2})
    grouping = group_bills(
        [
            ReportSittingDateTitleRow(report_id, sitting_date, title)
            for report_id, sitting_date, title in dated_titles
        ],
        first_reading_report_ids,
        third_reading_report_ids,
        [],
        [],
        [
            ReportSittingDateTitleRow(report_id, sitting_date, title)
            for report_id, sitting_date, title in dated_titles
        ],
        [],
        [],
        [],
    )

    placement = _place(
        [
            _report_row(report_id, f"report-{report_id}", sitting_date, title)
            for report_id, sitting_date, title in dated_titles
        ],
        first_reading_report_ids=first_reading_report_ids,
        third_reading_report_ids=third_reading_report_ids,
    )

    assert sorted(
        sorted(bill_group.report_ids) for bill_group in grouping.bill_groups
    ) == sorted(
        sorted(report_row.id for report_row in placed_bill.report_rows)
        for placed_bill in placement.placed_bills
    )
