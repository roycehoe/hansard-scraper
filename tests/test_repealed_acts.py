import re
from datetime import date

import pytest

from exceptions import HansardRepealedActsListingError
from schemas.repealed_acts_plan import PlannedRepealedActEntry
from services.repealed_acts import (
    build_planned_entry,
    get_enactment_year,
    get_first_planned_entries,
    get_last_version_date,
    get_repeal_date,
    get_sso_code,
)
from utils.sso_listing import ActListingRow

_LINK = "/Act/AA1987/Repealed/20040401?DocDate=20011231"


def _build_planned_entry(sso_code: str, capture_url: str) -> PlannedRepealedActEntry:
    return PlannedRepealedActEntry(
        printed_title="Title",
        printed_chapter=None,
        link=f"/Act/{sso_code}/Repealed/20040401?DocDate=20011231",
        sso_code=sso_code,
        enactment_year=None,
        repeal_date=date(2004, 4, 1),
        last_version_date=date(2001, 12, 31),
        capture_url=capture_url,
    )


def test_get_sso_code_reads_the_code_of_the_link() -> None:
    assert get_sso_code(_LINK) == "AA1987"


def test_get_repeal_date_reads_the_date_after_repealed() -> None:
    assert get_repeal_date(_LINK) == date(2004, 4, 1)


def test_get_last_version_date_reads_docdate() -> None:
    assert get_last_version_date(_LINK) == date(2001, 12, 31)


def test_get_last_version_date_reads_the_first_eight_of_fourteen_digits() -> None:
    link = "/Act/AA1987/Repealed/20040401?DocDate=20011231170000"

    assert get_last_version_date(link) == date(2001, 12, 31)


def test_link_functions_raise_on_another_shape() -> None:
    link = "/Act/AA1987/Published/20040401?DocDate=20011231"

    with pytest.raises(HansardRepealedActsListingError, match=re.escape(link)):
        get_sso_code(link)


def test_get_repeal_date_raises_on_an_impossible_date() -> None:
    link = "/Act/AA1987/Repealed/20041399?DocDate=20011231"

    with pytest.raises(HansardRepealedActsListingError, match="impossible"):
        get_repeal_date(link)


def test_get_last_version_date_raises_on_an_impossible_date() -> None:
    link = "/Act/AA1987/Repealed/20040401?DocDate=20011399"

    with pytest.raises(HansardRepealedActsListingError, match="impossible"):
        get_last_version_date(link)


def test_get_enactment_year_reads_the_trailing_four_digits() -> None:
    sso_codes = ["AA1987", "FSFY2001A2002", "COVID19TMSRMA2020"]

    assert [get_enactment_year(sso_code) for sso_code in sso_codes] == [
        1987,
        2002,
        2020,
    ]


def test_get_enactment_year_is_none_without_trailing_digits() -> None:
    assert get_enactment_year("CAAUNKNOWN") is None


def test_build_planned_entry_carries_the_code_year_and_dates() -> None:
    act_listing_row = ActListingRow("Accountants Act (Repealed)", _LINK, "Cap. 2")

    planned_entry = build_planned_entry(act_listing_row, "https://archive/1")

    assert planned_entry.printed_chapter == "Cap. 2"
    assert (planned_entry.sso_code, planned_entry.enactment_year) == ("AA1987", 1987)
    assert planned_entry.repeal_date == date(2004, 4, 1)
    assert planned_entry.last_version_date == date(2001, 12, 31)
    assert planned_entry.capture_url == "https://archive/1"


def test_dedupe_keeps_the_first_capture_of_an_sso_code() -> None:
    planned_entries = [
        _build_planned_entry("AA1987", "https://archive/first"),
        _build_planned_entry("AA1987", "https://archive/second"),
        _build_planned_entry("BB1990", "https://archive/second"),
    ]

    first_entries = get_first_planned_entries(planned_entries)

    assert [(entry.sso_code, entry.capture_url) for entry in first_entries] == [
        ("AA1987", "https://archive/first"),
        ("BB1990", "https://archive/second"),
    ]
