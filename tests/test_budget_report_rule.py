from datetime import datetime, timedelta

from services.bill import (
    SupplyBillWindow,
    get_single_supply_bill_index,
    get_supply_bill_indexes_for_budget_report,
    is_main_supply_title_key,
)

_FIRST_DATE = datetime(2025, 3, 1)
_LAST_DATE = datetime(2025, 3, 20)
_ONLY_BILL_INDEX = 5


def _window(bill_index: int, is_main: bool) -> SupplyBillWindow:
    return SupplyBillWindow(bill_index, is_main, _FIRST_DATE, _LAST_DATE)


def test_a_head_report_in_the_window_attaches_to_the_supply_bill() -> None:
    assert get_supply_bill_indexes_for_budget_report(
        "BUDGET, Head B", datetime(2025, 3, 10), [_window(4, is_main=True)]
    ) == [4]


def test_a_supplementary_report_attaches_to_the_supplementary_bill_only() -> None:
    windows = [_window(1, is_main=True), _window(2, is_main=False)]

    assert get_supply_bill_indexes_for_budget_report(
        "Supplementary Estimates", datetime(2025, 3, 10), windows
    ) == [2]


def test_two_supplementary_bills_in_one_window_give_no_single_index() -> None:
    windows = [_window(2, is_main=False), _window(3, is_main=False)]

    bill_indexes = get_supply_bill_indexes_for_budget_report(
        "Supplementary Estimates", datetime(2025, 3, 10), windows
    )

    assert bill_indexes == [2, 3]
    assert get_single_supply_bill_index(bill_indexes) is None
    assert get_single_supply_bill_index([_ONLY_BILL_INDEX]) == _ONLY_BILL_INDEX
    assert get_single_supply_bill_index([]) is None


def test_the_window_opens_45_days_before_the_first_report() -> None:
    windows = [_window(0, is_main=True)]

    assert get_supply_bill_indexes_for_budget_report(
        "BUDGET, Head B", _FIRST_DATE - timedelta(days=45), windows
    ) == [0]
    assert (
        get_supply_bill_indexes_for_budget_report(
            "BUDGET, Head B", _FIRST_DATE - timedelta(days=46), windows
        )
        == []
    )


def test_the_window_closes_30_days_after_the_last_report() -> None:
    windows = [_window(0, is_main=True)]

    assert get_supply_bill_indexes_for_budget_report(
        "BUDGET, Head B", _LAST_DATE + timedelta(days=30), windows
    ) == [0]
    assert (
        get_supply_bill_indexes_for_budget_report(
            "BUDGET, Head B", _LAST_DATE + timedelta(days=31), windows
        )
        == []
    )


def test_main_supply_title_keys() -> None:
    assert is_main_supply_title_key("supplybill")
    assert is_main_supply_title_key("supplyfy2002bill")
    assert is_main_supply_title_key("appropriationbill")
    assert is_main_supply_title_key("supplyno2bill")
    assert not is_main_supply_title_key("supplementarysupplybill")
    assert not is_main_supply_title_key("finalsupplybill")
