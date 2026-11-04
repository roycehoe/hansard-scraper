import re
from datetime import date
from pathlib import Path
from typing import Optional

import pytest

from enums import ActHistoryDefect, ActHistoryEntryKind
from exceptions import HansardActHistoryError
from services.act_history import (
    HistoryEntryBlock,
    parse_history_entry,
    split_history_entries,
)

_FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "act_history"
_FIRST_ENTRY_HEAD = re.compile(r"(?m)^(LEGISLATIVE HISTORY\n\s?)\d{1,3}\.")


def _read_fixture(name: str) -> str:
    # NOTE: a fixture is one entry cut from the middle of a list, so it is renumbered as entry 1
    return _FIRST_ENTRY_HEAD.sub(
        r"\g<1>1.",
        (_FIXTURE_DIRECTORY / f"{name}.txt").read_text(encoding="utf8"),
        count=1,
    )


@pytest.mark.parametrize(
    (
        "fixture_name",
        "kind",
        "printed_law_number",
        "printed_title",
        "printed_bill_number",
        "dates",
        "defects",
    ),
    [
        (
            "amendments_by_qualifier",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance 71 of 1959",
            "Transfer of Powers Ordinance, 1959",
            "30/1959",
            (date(1959, 9, 22), date(1959, 11, 11), date(1959, 11, 11), None),
            [],
        ),
        (
            "amendments_qualifier_above_ordinance",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance 37 of 1952",
            "Law Revision (Penalties Amendment) Ordinance, 1952",
            "32/1952",
            (
                date(1952, 9, 16),
                date(1952, 10, 14),
                date(1952, 10, 14),
                date(1955, 4, 30),
            ),
            [],
        ),
        (
            "bill_family_ordinance_with_gazette_number_and_note",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance 24 of 1934",
            "Probate and Administration Ordinance, 1934",
            None,
            (date(1934, 2, 12), date(1934, 4, 16), date(1934, 5, 28), date(1935, 1, 1)),
            [],
        ),
        (
            "bill_family_recent_act",
            ActHistoryEntryKind.ACT,
            "Act 18 of 2019",
            "Protection from Online Falsehoods and Manipulation Act 2019",
            "10/2019",
            (date(2019, 4, 1), date(2019, 5, 7), date(2019, 5, 8), date(2019, 10, 2)),
            [],
        ),
        (
            "british_military_administration_proclamation",
            ActHistoryEntryKind.OTHER,
            "British Military Administration G.N. No. 12/1945",
            "Food Control Proclamation (Proclamation No. 10)",
            None,
            (None, None, None, date(1945, 11, 2)),
            [],
        ),
        (
            "capital_letter_block_after_entry",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance 39 of 1952",
            "Singapore Legislative Council Elections (Amendment No. 2) Ordinance, 1952",
            "38/1952",
            (
                date(1952, 11, 18),
                date(1952, 11, 18),
                date(1952, 11, 18),
                date(1952, 11, 22),
            ),
            [],
        ),
        (
            "consequential_amendments_qualifier",
            ActHistoryEntryKind.ACT,
            "Act 39 of 1999",
            "Police Force (Amendment) Act 1999",
            "32/99",
            (
                date(1999, 10, 11),
                date(1999, 11, 23),
                date(1999, 11, 23),
                date(2000, 1, 10),
            ),
            [ActHistoryDefect.PAGE_BREAK_NOISE],
        ),
        (
            "date_family_ordinance_with_bill_number",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance 25 of 1958",
            "Criminal Law (Temporary Provisions) (Amendment) Ordinance 1958",
            "165/1958",
            (
                date(1958, 8, 13),
                date(1958, 8, 13),
                date(1958, 8, 13),
                date(1958, 8, 15),
            ),
            [],
        ),
        (
            "date_family_ordinance_without_bill_number",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance 26 of 1955",
            "Criminal Law (Temporary Provisions) Ordinance 1955",
            None,
            (
                date(1955, 8, 18),
                date(1955, 9, 22),
                date(1955, 9, 22),
                date(1955, 10, 12),
            ),
            [],
        ),
        (
            "empty_value",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance III of 1872",
            "Penal Code Amendment Ordinance, 1872",
            None,
            (
                date(1872, 8, 15),
                date(1872, 8, 20),
                date(1872, 8, 22),
                date(1872, 9, 16),
            ),
            [ActHistoryDefect.EMPTY_VALUE],
        ),
        (
            "english_act",
            ActHistoryEntryKind.OTHER,
            "6 Edw. VII, c. 41",
            "Marine Insurance Act, 1906",
            None,
            (None, None, None, date(1907, 1, 1)),
            [],
        ),
        (
            "english_act_two_regnal_years_elizabeth",
            ActHistoryEntryKind.OTHER,
            "8 & 9 Eliz. II, c. 46",
            "Corporate Bodies’ Contracts Act, 1960",
            None,
            (None, None, None, date(1960, 7, 29)),
            [],
        ),
        (
            "english_act_two_regnal_years_george",
            ActHistoryEntryKind.OTHER,
            "22 & 23 Geo. 5, c. 39",
            "Extradition Act, 1932",
            None,
            (None, None, None, date(1932, 7, 12)),
            [],
        ),
        (
            "english_act_two_regnal_years_victoria",
            ActHistoryEntryKind.OTHER,
            "33 & 34 Vict., c. 52",
            "The Extradition Act, 1870",
            None,
            (None, None, None, date(1870, 8, 9)),
            [],
        ),
        (
            "federal_legal_notice",
            ActHistoryEntryKind.SUBSIDIARY_LEGISLATION,
            "L.N. 231/1963 (G.N. Sp. No. S 4/1963)",
            "Modification of Laws (Internal Security and Public Order) (Singapore) Order, 1963",
            None,
            (None, None, None, date(1963, 9, 16)),
            [],
        ),
        (
            "first_and_second_readings_not_available",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance 4 of 1948",
            "Probate and Administration (Amendment) Ordinance, 1948",
            None,
            (None, None, date(1948, 1, 29), date(1948, 2, 7)),
            [ActHistoryDefect.NO_DATE_PRINTED],
        ),
        (
            "first_second_and_third_readings_wrapped_label",
            ActHistoryEntryKind.ACT,
            "Act 19 of 1975",
            "Companies (Amendment) Act 1975",
            "44/75",
            (
                date(1975, 8, 19),
                date(1975, 8, 19),
                date(1975, 8, 19),
                date(1975, 8, 23),
            ),
            [],
        ),
        (
            "gazette_notification_with_space",
            ActHistoryEntryKind.SUBSIDIARY_LEGISLATION,
            "G. N. No. S 121/1971",
            "Criminal Law (Temporary Provisions) (Essential Services) Notification 1971",
            None,
            (None, None, None, date(1971, 4, 15)),
            [],
        ),
        (
            "gazette_notification_with_special_number",
            ActHistoryEntryKind.SUBSIDIARY_LEGISLATION,
            "G.N. Sp. No. S 1/1963",
            "Sabah, Sarawak and Singapore (State Constitutions) Order in Council 1963",
            None,
            (None, None, None, date(1963, 9, 16)),
            [],
        ),
        (
            "malayan_ordinance",
            ActHistoryEntryKind.OTHER,
            "M. Ordinance 7 of 1948",
            "Interpretation and General Clauses Ordinance, 1948",
            None,
            (None, None, None, date(1948, 1, 31)),
            [],
        ),
        (
            "malaysian_ordinance",
            ActHistoryEntryKind.OTHER,
            "Malaysian Ordinance 22 of 1964",
            "Criminal Law (Temporary Provisions) (Amendment) Ordinance 1964",
            None,
            (date(1964, 7, 6), date(1964, 7, 14), date(1964, 7, 14), date(1964, 7, 30)),
            [ActHistoryDefect.PAGE_BREAK_NOISE],
        ),
        (
            "missing_third_reading",
            ActHistoryEntryKind.ACT,
            "Act 15 of 2019",
            "Criminal Law Reform Act 2019",
            "6/2019",
            (date(2019, 2, 11), date(2019, 5, 6), None, date(2020, 1, 1)),
            [ActHistoryDefect.PAGE_BREAK_NOISE, ActHistoryDefect.MISSING_READING],
        ),
        (
            "missing_year",
            ActHistoryEntryKind.ACT,
            "Act 35 of 2024",
            "Income Tax (Amendment) Act 2024",
            "32/2024",
            (None, date(2024, 10, 15), date(2024, 10, 15), date(2024, 1, 1)),
            [ActHistoryDefect.PAGE_BREAK_NOISE, ActHistoryDefect.MISSING_YEAR],
        ),
        (
            "multiple_commencement_dates",
            ActHistoryEntryKind.ACT,
            "Act 30 of 2023",
            "Income Tax (Amendment) Act 2023",
            "30/2023",
            (
                date(2023, 9, 18),
                date(2023, 10, 3),
                date(2023, 10, 3),
                date(2023, 2, 15),
            ),
            [],
        ),
        (
            "numeric_reading_dates_two_digit_year",
            ActHistoryEntryKind.ACT,
            "Act 9 of 1999",
            "Environmental Pollution Control Act 1999",
            "2/99",
            (date(1999, 1, 20), date(1999, 2, 11), date(1999, 2, 11), date(1999, 4, 1)),
            [],
        ),
        (
            "numeric_reading_dates_wrapped_publication_bracket",
            ActHistoryEntryKind.ACT,
            "Act 4 of 2002",
            "National Environment Agency Act 2002",
            "13/2002",
            (date(2002, 5, 3), date(2002, 5, 24), date(2002, 5, 24), date(2002, 7, 1)),
            [],
        ),
        (
            "numeric_reading_dates_with_date_footer",
            ActHistoryEntryKind.ACT,
            "Act 9 of 1999",
            "Environmental Pollution Control Act 1999",
            "2/99",
            (date(1999, 1, 20), date(1999, 2, 11), date(1999, 2, 11), date(1999, 4, 1)),
            [ActHistoryDefect.PAGE_BREAK_NOISE],
        ),
        (
            "page_break_inside_entry",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance 17 of 1940",
            "Probate and Administration (Amendment) Ordinance, 1940",
            None,
            (date(1940, 2, 12), date(1940, 4, 22), date(1940, 4, 22), date(1940, 5, 8)),
            [ActHistoryDefect.PAGE_BREAK_NOISE],
        ),
        (
            "rectification_order_with_publication_line",
            ActHistoryEntryKind.SUBSIDIARY_LEGISLATION,
            "G.N. No. S 40/2022",
            "Revised Edition of the Laws (Rectification of Acts) Order 2022",
            None,
            (None, None, None, date(2021, 12, 31)),
            [],
        ),
        (
            "reprint",
            ActHistoryEntryKind.OTHER,
            "1966 Reprint",
            "The Constitution of Singapore",
            None,
            (None, None, None, None),
            [],
        ),
        (
            "revised_edition",
            ActHistoryEntryKind.REVISED_EDITION,
            "1970 Revised Edition",
            "Criminal Law (Temporary Provisions) Act (Cap. 112)",
            None,
            (None, None, None, date(1971, 4, 15)),
            [],
        ),
        (
            "roman_numbered_act",
            ActHistoryEntryKind.ACT,
            "Act XIV of 1867",
            "Interpretation Act, 1867",
            None,
            (date(1867, 6, 26), date(1867, 6, 26), date(1867, 7, 1), date(1867, 7, 1)),
            [],
        ),
        (
            "roman_numbered_ordinance",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance XIV of 1904",
            "The Morphine Ordinance 1904",
            None,
            (
                date(1904, 9, 16),
                date(1904, 9, 23),
                date(1904, 10, 7),
                date(1904, 10, 7),
            ),
            [ActHistoryDefect.PAGE_BREAK_NOISE],
        ),
        (
            "second_reading_and_second_and_third_readings",
            ActHistoryEntryKind.ACT,
            "Act 15 of 2010",
            "Criminal Procedure Code 2010",
            "11/2010",
            (date(2010, 4, 26), date(2010, 5, 18), date(2010, 5, 19), date(2011, 1, 2)),
            [ActHistoryDefect.PAGE_BREAK_NOISE],
        ),
        (
            "select_committee_dates",
            ActHistoryEntryKind.ACT,
            "Act 42 of 1967",
            "Companies Act 1967",
            "58/66",
            (
                date(1966, 12, 5),
                date(1966, 12, 21),
                date(1967, 12, 21),
                date(1967, 12, 29),
            ),
            [],
        ),
        (
            "select_committee_report_line",
            ActHistoryEntryKind.ACT,
            "Act 19 of 1969",
            "Constitution (Amendment) Act, 1969",
            "5/1969",
            (date(1969, 4, 8), date(1969, 6, 12), date(1969, 12, 23), date(1970, 1, 9)),
            [],
        ),
        (
            "qualifier_not_closed",
            ActHistoryEntryKind.ACT,
            "Act 21 of 1973",
            "Statutes of the Republic of Singapore (Miscellaneous Amendments) Act, 1973",
            "16/1973",
            (date(1973, 3, 7), date(1973, 3, 20), date(1973, 3, 20), date(1973, 4, 6)),
            [ActHistoryDefect.PAGE_BREAK_NOISE],
        ),
        (
            "qualifier_with_nested_parentheses",
            ActHistoryEntryKind.ACT,
            "Act 6 of 1994",
            "Revised Edition of the Laws (Amendment) Act 1994",
            "7/1994",
            (date(1994, 3, 16), date(1994, 5, 23), date(1994, 5, 23), date(1994, 7, 1)),
            [ActHistoryDefect.PAGE_BREAK_NOISE],
        ),
        (
            "related_amendments_qualifier",
            ActHistoryEntryKind.ACT,
            "Act 10 of 2006",
            "Casino Control Act 2006",
            "3/2006",
            (date(2006, 1, 16), date(2006, 2, 14), date(2006, 2, 14), date(2008, 4, 2)),
            [],
        ),
        (
            "ordinance_with_three_digit_year",
            ActHistoryEntryKind.ORDINANCE,
            "Ordinance 63 of 193",
            "Statute Law Revision Ordinance, 1935",
            None,
            (
                date(1935, 11, 20),
                date(1935, 12, 9),
                date(1935, 12, 9),
                date(1935, 12, 31),
            ),
            [],
        ),
        (
            "act_with_placeholder_number",
            ActHistoryEntryKind.ACT,
            "Act N of 2019",
            "Work Injury Compensation Act 2019",
            "21/2019",
            (date(2019, 8, 5), date(2019, 9, 3), date(2019, 9, 3), date(2020, 9, 1)),
            [],
        ),
    ],
)
def test_entry_shape_is_read_as_printed(
    fixture_name: str,
    kind: ActHistoryEntryKind,
    printed_law_number: str,
    printed_title: str,
    printed_bill_number: Optional[str],
    dates: tuple[Optional[date], Optional[date], Optional[date], Optional[date]],
    defects: list[ActHistoryDefect],
) -> None:
    (block,) = split_history_entries("CODE", _read_fixture(fixture_name))

    entry = parse_history_entry("CODE", block)

    assert entry.ordinal == 1
    assert entry.kind == kind
    assert entry.printed_law_number == printed_law_number
    assert entry.printed_title == printed_title
    assert entry.printed_bill_number == printed_bill_number
    assert (
        entry.first_reading_date,
        entry.second_reading_date,
        entry.third_reading_date,
        entry.commencement_date,
    ) == dates
    assert entry.defects == defects


def test_a_united_kingdom_act_is_an_entry_of_kind_other() -> None:
    blocks = split_history_entries(
        "CODE", _read_fixture("united_kingdom_act_between_ordinance_and_order")
    )

    entries = [parse_history_entry("CODE", block) for block in blocks]

    assert [(entry.ordinal, entry.kind) for entry in entries] == [
        (1, ActHistoryEntryKind.REVISED_EDITION),
        (2, ActHistoryEntryKind.OTHER),
        (3, ActHistoryEntryKind.SUBSIDIARY_LEGISLATION),
    ]
    assert entries[1].printed_law_number == "U.K. 1949, c. 67"
    assert entries[1].printed_title == "Civil Aviation Act, 1949"
    assert entries[1].commencement_date == date(1949, 11, 24)
    assert (
        entries[2].printed_title
        == "Colonial Civil Aviation (Application of Act) Order, 1952"
    )


def test_an_indian_act_is_an_entry_of_kind_other() -> None:
    blocks = split_history_entries(
        "CODE", _read_fixture("indian_act_and_revised_edition_ordinance")
    )

    entries = [parse_history_entry("CODE", block) for block in blocks]

    assert [
        (
            entry.kind,
            entry.printed_law_number,
            entry.printed_title,
            entry.commencement_date,
        )
        for entry in entries
    ] == [
        (
            ActHistoryEntryKind.OTHER,
            "Indian Act XXI of 1865",
            "The Parsi Intestate Succession Act",
            date(1865, 4, 10),
        ),
        (
            ActHistoryEntryKind.REVISED_EDITION,
            "1920 Revised Edition",
            "Ordinance No. 10 (Parsee Intestate Succession)",
            date(1921, 11, 28),
        ),
    ]


def test_a_federated_malay_states_enactment_and_chapter_are_entries_of_kind_other() -> (
    None
):
    blocks = split_history_entries(
        "CODE", _read_fixture("federated_malay_states_enactment_and_chapter")
    )

    entries = [parse_history_entry("CODE", block) for block in blocks]

    assert [
        (
            entry.kind,
            entry.printed_law_number,
            entry.printed_title,
            entry.commencement_date,
        )
        for entry in entries
    ] == [
        (
            ActHistoryEntryKind.OTHER,
            "M. Enactment 5 of 1905",
            "The Military Manœuvres Enactment, 1905",
            date(1905, 4, 28),
        ),
        (
            ActHistoryEntryKind.OTHER,
            "F.M.S. Chapter 43",
            "Military Manœuvres Enactment",
            date(1935, 2, 28),
        ),
        (
            ActHistoryEntryKind.SUBSIDIARY_LEGISLATION,
            "L.N. 233/1963 (G.N. Sp. No. S 5/1963)",
            "Modification of Laws (Armed Forces) (Singapore) Order, 1963",
            date(1963, 9, 16),
        ),
    ]


def test_a_legal_notice_with_no_gazette_bracket_or_no_closing_parenthesis_is_read() -> (
    None
):
    blocks = split_history_entries(
        "CODE",
        _read_fixture("legal_notice_without_gazette_bracket_or_closing_parenthesis"),
    )

    entries = [parse_history_entry("CODE", block) for block in blocks]

    assert [
        (entry.kind, entry.printed_law_number, entry.printed_title) for entry in entries
    ] == [
        (
            ActHistoryEntryKind.SUBSIDIARY_LEGISLATION,
            "L.N. 70/1964",
            "Modification of Laws (National Service) (Extension) Order, 1964",
        ),
        (
            ActHistoryEntryKind.SUBSIDIARY_LEGISLATION,
            "L.N. 455/1964 (G.N. Sp. No. S 2/1965",
            "Modification of Laws (Debtors) (Borneo States and Singapore) Order, 1964",
        ),
        (
            ActHistoryEntryKind.SUBSIDIARY_LEGISLATION,
            "L.N. 133/1965 (G.N. Sp. No. S 67/1965",
            "Modification of Laws (Insurance) (Extension) Order, 1964",
        ),
        (
            ActHistoryEntryKind.SUBSIDIARY_LEGISLATION,
            "L.N. 296/1964 (G.N. Sp. No. S 205/1964)",
            "Air Navigation Ordinance, 1952 (Extension) Order, 1964",
        ),
    ]


def test_a_straits_settlements_gazette_notification_is_an_entry_of_kind_other() -> None:
    blocks = split_history_entries(
        "CODE", _read_fixture("straits_settlements_gazette_notifications")
    )

    entries = [parse_history_entry("CODE", block) for block in blocks]

    assert [
        (
            entry.kind,
            entry.printed_law_number,
            entry.printed_title,
            entry.commencement_date,
        )
        for entry in entries
    ] == [
        (
            ActHistoryEntryKind.OTHER,
            "S.S.G.G. (E) No. 64/1908",
            "Proclamation 1908",
            date(1908, 11, 28),
        ),
        (
            ActHistoryEntryKind.OTHER,
            "S.S.G.G. (E) No. 6/1909",
            "Proclamation 1909",
            date(1909, 2, 1),
        ),
    ]


def test_a_legal_notice_printed_with_a_space_between_its_initials_is_read() -> None:
    blocks = split_history_entries(
        "CODE", _read_fixture("legal_notice_with_spaced_initials")
    )

    entries = [parse_history_entry("CODE", block) for block in blocks]

    assert [
        (
            entry.kind,
            entry.printed_law_number,
            entry.printed_title,
            entry.commencement_date,
        )
        for entry in entries
    ] == [
        (
            ActHistoryEntryKind.SUBSIDIARY_LEGISLATION,
            "L. N. 231/1963 (G.N. Sp. No. S 4/1963)",
            "Modification of Laws (Internal Security and Public Order) (Singapore) Order, 1963",
            date(1963, 9, 16),
        ),
        (
            ActHistoryEntryKind.REVISED_EDITION,
            "1970 Revised Edition",
            "Visiting Forces Act (Chapter 237)",
            date(1971, 7, 31),
        ),
    ]


def test_a_qualifier_that_is_not_closed_stays_in_the_printed_text() -> None:
    (block,) = split_history_entries("CODE", _read_fixture("qualifier_not_closed"))

    printed_text = parse_history_entry("CODE", block).printed_text

    assert (
        "(Amendments made by section 2 read with the Schedule to the above Act"
        in printed_text
    )


def test_printed_text_keeps_the_entry_lines_and_drops_page_break_noise() -> None:
    (block,) = split_history_entries("CODE", _read_fixture("page_break_inside_entry"))

    printed_lines = parse_history_entry("CODE", block).printed_text.splitlines()

    assert printed_lines[0] == (
        " 1. Ordinance 17 of 1940 — Probate and Administration (Amendment)"
    )
    assert not any("Informal Consolidation" in line for line in printed_lines)
    assert [line.split() for line in printed_lines[-2:]] == [
        ["Third", "Reading", ":", "22", "April", "1940"],
        ["Commencement", ":", "8", "May", "1940"],
    ]


def test_a_date_footer_on_its_own_line_is_noise_and_not_part_of_the_entry() -> None:
    (block,) = split_history_entries(
        "CODE", _read_fixture("numeric_reading_dates_with_date_footer")
    )

    assert "31.12.2021" not in "\n".join(block.lines)
    assert block.has_page_break_noise


def test_a_two_digit_year_pivots_to_the_century_at_fifty() -> None:
    blocks = split_history_entries(
        "CODE",
        "LEGISLATIVE HISTORY\n"
        " 1. Act 1 of 1949 — A Act 1949\n"
        "     First Reading                  :    1.2.49\n"
        "     Second Reading                 :    1.3.50\n"
        "     Third Reading                  :    1.4.00\n"
        "     Commencement                   :    1.5.99\n",
    )

    entry = parse_history_entry("CODE", blocks[0])

    assert (
        entry.first_reading_date,
        entry.second_reading_date,
        entry.third_reading_date,
        entry.commencement_date,
    ) == (date(2049, 2, 1), date(1950, 3, 1), date(2000, 4, 1), date(1999, 5, 1))


def test_a_numeric_date_that_is_not_a_calendar_date_raises_with_the_act_code() -> None:
    (block,) = split_history_entries(
        "ZZA1999",
        "LEGISLATIVE HISTORY\n"
        " 1. Act 1 of 1999 — A Act 1999\n"
        "     First Reading                  :    31.2.99\n",
    )

    with pytest.raises(
        HansardActHistoryError, match="Act ZZA1999: entry 1 prints the date 31.2.99"
    ):
        parse_history_entry("ZZA1999", block)


def test_note_under_the_commencement_value_is_not_part_of_the_date() -> None:
    (block,) = split_history_entries(
        "CODE", _read_fixture("bill_family_ordinance_with_gazette_number_and_note")
    )

    assert any(
        "Note: Previously in the Civil Procedure Code" in line for line in block.lines
    )
    assert parse_history_entry("CODE", block).commencement_date == date(1935, 1, 1)


def test_capital_letter_block_does_not_join_the_entry() -> None:
    (block,) = split_history_entries(
        "CODE", _read_fixture("capital_letter_block_after_entry")
    )

    assert "PART 2" not in "\n".join(block.lines)


def test_an_act_with_no_legislative_history_has_no_entries() -> None:
    assert (
        split_history_entries("CODE", "ONLINE CRIMINAL HARMS ACT 2023\n\nPart 1\n")
        == []
    )


def test_an_entry_number_out_of_sequence_raises_with_the_act_code() -> None:
    text = "LEGISLATIVE HISTORY\n 1. Act 1 of 1950 — A Act 1950\n 3. Act 3 of 1952 — C Act 1952\n"

    with pytest.raises(
        HansardActHistoryError, match="Act ZZA1950: entry 3 follows entry 1"
    ):
        split_history_entries("ZZA1950", text)


def test_an_entry_head_in_no_known_shape_raises_with_the_act_code_and_entry_number() -> (
    None
):
    text = "LEGISLATIVE HISTORY\n 1. Act 1 of 1950 — A Act 1950\n 2. Act 2 of 1951 — B Act 1951\n"
    (first_block, _) = split_history_entries("ZZA1950", text)
    unreadable_block = HistoryEntryBlock(2, [" 2. Act two — B"], False)

    assert parse_history_entry("ZZA1950", first_block).ordinal == 1
    with pytest.raises(HansardActHistoryError, match="Act ZZA1950: entry 2"):
        parse_history_entry("ZZA1950", unreadable_block)
