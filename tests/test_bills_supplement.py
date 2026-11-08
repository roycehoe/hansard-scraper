from datetime import date

import pytest

from exceptions import HansardBillsSupplementError
from schemas.bills_supplement_plan import PlannedEntry
from services.bills_supplement import (
    build_planned_entry,
    get_bill_number,
    get_first_planned_entries,
    get_publication_date,
)
from utils.sso_listing import ListingRow


def _build_planned_entry(bill_number: str, link: str, capture_url: str) -> PlannedEntry:
    return PlannedEntry(
        printed_title="Title",
        printed_number="Bill 1 of 2000",
        link=link,
        pdf_link=None,
        pdf_size=None,
        bill_number=bill_number,
        publication_date=date(2000, 1, 1),
        capture_url=capture_url,
    )


def test_get_bill_number_reads_the_printed_number() -> None:
    assert get_bill_number("Bill 19 of 2016") == "19/2016"


def test_get_bill_number_raises_on_another_form() -> None:
    with pytest.raises(HansardBillsSupplementError, match="not 'Bill N of YYYY'"):
        get_bill_number("Bill 19/2016")


def test_get_publication_date_reads_the_digits_after_published() -> None:
    link = "/Bills-Supp/19-2016/Published/20160711?DocDate=20160711"

    assert get_publication_date(link) == date(2016, 7, 11)


def test_get_publication_date_raises_without_the_digits() -> None:
    with pytest.raises(HansardBillsSupplementError, match="no publication date"):
        get_publication_date("/Bills-Supp/19-2016/Published/?DocDate=20160711")


def test_get_publication_date_raises_on_an_impossible_date() -> None:
    with pytest.raises(HansardBillsSupplementError, match="impossible"):
        get_publication_date("/Bills-Supp/19-2016/Published/20161399")


def test_build_planned_entry_carries_the_number_and_date() -> None:
    listing_row = ListingRow(
        "Title", "Bill 2 of 2026", "/b/Published/20260203", None, None
    )

    planned_entry = build_planned_entry(listing_row, "https://archive/1")

    assert planned_entry.bill_number == "2/2026"
    assert planned_entry.publication_date == date(2026, 2, 3)
    assert planned_entry.capture_url == "https://archive/1"


def test_dedupe_keeps_the_first_capture_of_a_bill_number_and_link() -> None:
    planned_entries = [
        _build_planned_entry("1/2000", "/a", "https://archive/first"),
        _build_planned_entry("1/2000", "/a", "https://archive/second"),
        _build_planned_entry("1/2000", "/b", "https://archive/second"),
        _build_planned_entry("2/2000", "/a", "https://archive/second"),
    ]

    first_entries = get_first_planned_entries(planned_entries)

    assert [
        (entry.bill_number, entry.link, entry.capture_url) for entry in first_entries
    ] == [
        ("1/2000", "/a", "https://archive/first"),
        ("1/2000", "/b", "https://archive/second"),
        ("2/2000", "/a", "https://archive/second"),
    ]
