from datetime import date

import pytest

from exceptions import HansardActsSupplementError
from schemas.acts_supplement_plan import PlannedActsSupplementEntry
from services.acts_supplement import (
    build_planned_entry,
    get_act_number,
    get_first_planned_entries,
    get_publication_date,
)
from utils.sso_listing import ListingRow


def _build_planned_entry(
    act_number: str, link: str, capture_url: str
) -> PlannedActsSupplementEntry:
    return PlannedActsSupplementEntry(
        printed_title="Title",
        printed_number="Act 1 of 2000",
        link=link,
        pdf_link=None,
        pdf_size=None,
        act_number=act_number,
        publication_date=date(2000, 1, 1),
        capture_url=capture_url,
    )


def test_get_act_number_reads_the_printed_number() -> None:
    assert get_act_number("Act 19 of 2016") == "19/2016"


def test_get_act_number_raises_on_another_form() -> None:
    with pytest.raises(HansardActsSupplementError, match="not 'Act N of YYYY'"):
        get_act_number("Act 19/2016")


def test_get_publication_date_reads_eight_digits_of_docdate() -> None:
    assert get_publication_date(
        "/Acts-Supp/1-2011/Published/20111231?DocDate=20110103"
    ) == date(2011, 1, 3)


def test_get_publication_date_reads_the_first_eight_of_fourteen_digits() -> None:
    link = "/Acts-Supp/1-2011/Published/20111231?DocDate=20110103170000"

    assert get_publication_date(link) == date(2011, 1, 3)


def test_get_publication_date_ignores_the_published_segment() -> None:
    link = "/Acts-Supp/1-2011/Published/20150505?DocDate=20110103170000"

    assert get_publication_date(link) == date(2011, 1, 3)


def test_get_publication_date_raises_without_docdate() -> None:
    with pytest.raises(HansardActsSupplementError, match="no publication date"):
        get_publication_date("/Acts-Supp/1-2011/Published/20111231")


def test_get_publication_date_raises_on_an_impossible_date() -> None:
    with pytest.raises(HansardActsSupplementError, match="impossible"):
        get_publication_date("/Acts-Supp/1-2011/Published/20111231?DocDate=20111399")


def test_build_planned_entry_carries_the_number_and_date() -> None:
    listing_row = ListingRow(
        "Title",
        "Act 2 of 2026",
        "/a/Published/20261231?DocDate=20260203170000",
        None,
        None,
    )

    planned_entry = build_planned_entry(listing_row, "https://archive/1")

    assert planned_entry.act_number == "2/2026"
    assert planned_entry.publication_date == date(2026, 2, 3)
    assert planned_entry.capture_url == "https://archive/1"


def test_dedupe_keeps_the_first_capture_of_an_act_number_and_link() -> None:
    planned_entries = [
        _build_planned_entry("1/2000", "/a", "https://archive/first"),
        _build_planned_entry("1/2000", "/a", "https://archive/second"),
        _build_planned_entry("1/2000", "/b", "https://archive/second"),
        _build_planned_entry("2/2000", "/a", "https://archive/second"),
    ]

    first_entries = get_first_planned_entries(planned_entries)

    assert [
        (entry.act_number, entry.link, entry.capture_url) for entry in first_entries
    ] == [
        ("1/2000", "/a", "https://archive/first"),
        ("1/2000", "/b", "https://archive/second"),
        ("2/2000", "/a", "https://archive/second"),
    ]
