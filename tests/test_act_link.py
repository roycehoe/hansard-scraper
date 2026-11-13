from dataclasses import fields
from datetime import date, datetime

from crud.report import ReportSittingDateTitleRow
from enums import BillLinkSource
from populate.act_links import BillGroupingContext, build_bill_lookups_from_context
from services.act_link import (
    BillLink,
    BillLookups,
    LinkableBill,
    build_bill_lookups,
    get_bill_link,
)
from services.bill import group_bills
from utils.data_files import get_hand_kept_act_links
from utils.title_key import get_bill_title_key, get_title_key


def _build_linkable_bills(
    report_rows: list[ReportSittingDateTitleRow], third_reading_report_ids: set[int]
) -> BillLookups:
    report_id_to_sitting_date = {
        report_row.id: report_row.sitting_date.date() for report_row in report_rows
    }
    title_key_to_linkable_bills: dict[str, list[LinkableBill]] = {}
    grouping = group_bills(
        report_rows,
        frozenset(),
        frozenset(third_reading_report_ids),
        [],
        [],
        [],
        [],
        [],
        [],
    )
    for bill_index, bill_group in enumerate(grouping.bill_groups):
        title_key_to_linkable_bills.setdefault(bill_group.title_key, []).append(
            LinkableBill(
                bill_index,
                [
                    report_id_to_sitting_date[report_id]
                    for report_id in bill_group.report_ids
                ],
            )
        )
    return build_bill_lookups(title_key_to_linkable_bills, {})


_MONEYLENDERS_BILLS = _build_linkable_bills(
    [
        ReportSittingDateTitleRow(
            1, datetime(2005, 10, 17), "MONEYLENDERS (AMENDMENT) BILL"
        ),
        ReportSittingDateTitleRow(
            2, datetime(2006, 2, 20), "MONEYLENDERS (AMENDMENT) BILL"
        ),
    ],
    {1, 2},
)

_HAND_KEPT_ENTRY_COUNT = 11
_HAND_KEPT_ENTRIES = frozenset(
    {
        ("ABA1965", 10),
        ("NHBA1993", 1),
        ("CLTPA1955", 7),
        ("FSA1965", 1),
        ("IRASA1992", 5),
        ("PTA2005", 19),
        ("SAFA1972", 15),
        ("SFA2001", 3),
        ("SFA2001", 11),
        ("SWA1995", 2),
        ("TMA1998", 4),
    }
)


def test_entry_title_becomes_the_key_of_the_bill_title() -> None:
    assert get_bill_title_key(
        "Criminal Law (Temporary Provisions) (Amendment) Ordinance 1958"
    ) == get_title_key("CRIMINAL LAW (TEMPORARY PROVISIONS) (AMENDMENT) BILL")
    assert get_bill_title_key(
        "Probate and Administration Ordinance, 1934"
    ) == get_title_key("Probate and Administration Bill")
    assert get_bill_title_key("Companies Act 1967") == get_title_key("Companies Bill")
    assert get_bill_title_key("Criminal Procedure Code 2010") == get_title_key(
        "CRIMINAL PROCEDURE CODE BILL"
    )
    assert get_bill_title_key(
        "Singapore Legislative Council Elections (Amendment No. 2) Ordinance, 1952"
    ) == get_title_key("SINGAPORE LEGISLATIVE COUNCIL ELECTIONS (AMENDMENT NO. 2) BILL")


def test_a_leading_the_is_not_part_of_the_bill_title_key() -> None:
    assert get_bill_title_key(
        "The Health Sciences Authority Act 2001"
    ) == get_title_key("HEALTH SCIENCES AUTHORITY BILL")
    assert get_bill_title_key("Theatres Act 1958") == get_title_key("THEATRES BILL")


def test_a_trailing_chapter_is_not_part_of_the_bill_title_key() -> None:
    assert get_bill_title_key(
        "Building Maintenance and Strata Management Act (Chapter 30C)"
    ) == get_title_key("BUILDING MAINTENANCE AND STRATA MANAGEMENT BILL")
    assert get_bill_title_key("Companies Act 1967 (Chapter 50)") == get_title_key(
        "Companies Bill"
    )
    assert get_bill_title_key("Chapter Act 1950") == get_title_key("CHAPTER BILL")


def test_two_same_title_bills_link_to_the_bill_read_on_the_entry_dates() -> None:
    first_link = get_bill_link(
        "Moneylenders (Amendment) Act 2005",
        date(2005, 10, 17),
        None,
        None,
        _MONEYLENDERS_BILLS,
    )
    second_link = get_bill_link(
        "Moneylenders (Amendment) Act 2006",
        date(2006, 2, 20),
        None,
        None,
        _MONEYLENDERS_BILLS,
    )

    assert first_link == BillLink(0, BillLinkSource.FIRST_READING_DATE)
    assert second_link == BillLink(1, BillLinkSource.FIRST_READING_DATE)


def test_a_reading_one_day_off_still_links_and_two_days_off_does_not() -> None:
    assert get_bill_link(
        "Moneylenders (Amendment) Act 2006",
        date(2006, 2, 21),
        None,
        None,
        _MONEYLENDERS_BILLS,
    ) == BillLink(1, BillLinkSource.FIRST_READING_DATE)
    assert (
        get_bill_link(
            "Moneylenders (Amendment) Act 2006",
            date(2006, 2, 22),
            None,
            None,
            _MONEYLENDERS_BILLS,
        )
        is None
    )


def test_the_third_reading_date_is_tried_before_the_second() -> None:
    third_link = get_bill_link(
        "Moneylenders (Amendment) Act 2006",
        date(2006, 1, 1),
        date(2005, 10, 17),
        date(2006, 2, 20),
        _MONEYLENDERS_BILLS,
    )
    second_link = get_bill_link(
        "Moneylenders (Amendment) Act 2006",
        None,
        date(2006, 2, 20),
        date(2006, 1, 1),
        _MONEYLENDERS_BILLS,
    )

    assert third_link == BillLink(1, BillLinkSource.THIRD_READING_DATE)
    assert second_link == BillLink(1, BillLinkSource.SECOND_READING_DATE)


def test_a_no_2_sequel_read_on_other_dates_does_not_link_to_the_first_bill() -> None:
    title_key_to_linkable_bills = _build_linkable_bills(
        [
            ReportSittingDateTitleRow(
                1, datetime(2026, 3, 10), "Land Transport and Related Matters Bill"
            ),
        ],
        {1},
    )

    assert (
        get_bill_link(
            "Land Transport and Related Matters (No 2) Act 2026",
            date(2026, 9, 1),
            None,
            None,
            title_key_to_linkable_bills,
        )
        is None
    )


def test_an_entry_with_no_dates_links_to_nothing() -> None:
    assert (
        get_bill_link(
            "Moneylenders (Amendment) Act 2006", None, None, None, _MONEYLENDERS_BILLS
        )
        is None
    )


def _build_single_bill_lookups(
    title: str, first_reading_date: date, third_reading_date: date
) -> BillLookups:
    return _build_linkable_bills(
        [
            ReportSittingDateTitleRow(
                1, datetime.combine(first_reading_date, datetime.min.time()), title
            ),
            ReportSittingDateTitleRow(
                2, datetime.combine(third_reading_date, datetime.min.time()), title
            ),
        ],
        {2},
    )


def test_a_title_with_a_leading_the_links_to_the_bill_read_on_the_entry_dates() -> None:
    bill_lookups = _build_single_bill_lookups(
        "HEALTH SCIENCES AUTHORITY BILL", date(2001, 1, 12), date(2001, 2, 22)
    )

    assert get_bill_link(
        "The Health Sciences Authority Act 2001",
        date(2001, 1, 12),
        date(2001, 2, 22),
        date(2001, 2, 22),
        bill_lookups,
    ) == BillLink(0, BillLinkSource.FIRST_READING_DATE)


def test_a_title_with_a_leading_the_still_links_to_a_bill_that_keeps_the() -> None:
    bill_lookups = _build_single_bill_lookups(
        "The Society of Saint Maur Incorporation (Amendment) Bill",
        date(2017, 1, 9),
        date(2017, 3, 6),
    )

    assert get_bill_link(
        "The Society of Saint Maur Incorporation (Amendment) Act 2017",
        date(2017, 1, 9),
        None,
        date(2017, 3, 6),
        bill_lookups,
    ) == BillLink(0, BillLinkSource.FIRST_READING_DATE)


def test_a_title_with_a_trailing_chapter_links_to_the_bill_read_on_the_entry_dates() -> (
    None
):
    bill_lookups = _build_single_bill_lookups(
        "BUILDING MAINTENANCE AND STRATA MANAGEMENT BILL",
        date(2004, 9, 1),
        date(2004, 10, 19),
    )

    assert get_bill_link(
        "Building Maintenance and Strata Management Act (Chapter 30C)",
        date(2004, 9, 1),
        None,
        date(2004, 10, 19),
        bill_lookups,
    ) == BillLink(0, BillLinkSource.FIRST_READING_DATE)


def test_an_act_title_links_to_the_amendment_bill_read_on_the_same_dates() -> None:
    bill_lookups = _build_single_bill_lookups(
        "INCOME TAX (AMENDMENT) BILL", date(1998, 6, 29), date(1998, 7, 31)
    )

    assert get_bill_link(
        "Income Tax Act 1998",
        date(1998, 6, 29),
        date(1998, 7, 31),
        date(1998, 7, 31),
        bill_lookups,
    ) == BillLink(0, BillLinkSource.LOOSE_TITLE_READING_DATES)


def test_an_amendment_title_links_to_the_numbered_amendment_bill() -> None:
    bill_lookups = _build_single_bill_lookups(
        "Road Traffic (Amendment No. 2) Bill", date(2010, 3, 1), date(2010, 4, 5)
    )

    assert get_bill_link(
        "Road Traffic (Amendment) Act 2010",
        date(2010, 3, 1),
        None,
        date(2010, 4, 5),
        bill_lookups,
    ) == BillLink(0, BillLinkSource.LOOSE_TITLE_READING_DATES)


def test_a_title_links_to_the_bill_with_a_number_in_brackets() -> None:
    bill_lookups = _build_single_bill_lookups(
        "Statute Law Revision (No. 2) Bill", date(2012, 5, 7), date(2012, 6, 4)
    )

    assert get_bill_link(
        "Statute Law Revision Act 2012",
        date(2012, 5, 7),
        None,
        None,
        bill_lookups,
    ) == BillLink(0, BillLinkSource.LOOSE_TITLE_READING_DATES)


def test_two_bills_with_one_loose_title_and_the_same_report_day_link_to_nothing() -> (
    None
):
    bill_lookups = _build_linkable_bills(
        [
            ReportSittingDateTitleRow(
                1, datetime(2012, 5, 7), "Statute Law Revision (No. 2) Bill"
            ),
            ReportSittingDateTitleRow(
                2, datetime(2012, 5, 7), "Statute Law Revision (No. 3) Bill"
            ),
        ],
        {1, 2},
    )

    assert (
        get_bill_link(
            "Statute Law Revision Act 2012", date(2012, 5, 7), None, None, bill_lookups
        )
        is None
    )


def test_an_exact_title_match_wins_over_a_loose_one() -> None:
    bill_lookups = _build_linkable_bills(
        [
            ReportSittingDateTitleRow(
                1, datetime(2012, 5, 7), "Statute Law Revision (No. 2) Bill"
            ),
            ReportSittingDateTitleRow(
                2, datetime(2012, 5, 7), "Statute Law Revision Bill"
            ),
        ],
        {1, 2},
    )

    assert get_bill_link(
        "Statute Law Revision Act 2012", date(2012, 5, 7), None, None, bill_lookups
    ) == BillLink(1, BillLinkSource.FIRST_READING_DATE)


def _build_bills_read_on_the_same_dates(
    titles: list[str], first_reading_date: date, third_reading_date: date
) -> BillLookups:
    report_rows: list[ReportSittingDateTitleRow] = []
    third_reading_report_ids: set[int] = set()
    for report_id, title in enumerate(titles, start=1):
        report_rows.append(
            ReportSittingDateTitleRow(
                report_id * 2 - 1,
                datetime.combine(first_reading_date, datetime.min.time()),
                title,
            )
        )
        report_rows.append(
            ReportSittingDateTitleRow(
                report_id * 2,
                datetime.combine(third_reading_date, datetime.min.time()),
                title,
            )
        )
        third_reading_report_ids.add(report_id * 2)
    return _build_linkable_bills(report_rows, third_reading_report_ids)


def test_a_misprinted_title_links_to_nothing_by_rule() -> None:
    bill_lookups = _build_bills_read_on_the_same_dates(
        ["ANIMALS BILL", "FEEDSTUFFS BILL"], date(1964, 11, 19), date(1965, 6, 16)
    )

    assert (
        get_bill_link(
            "Feeding Stuffs Ordinance, 1965",
            date(1964, 11, 19),
            None,
            date(1965, 6, 16),
            bill_lookups,
        )
        is None
    )


def test_the_hand_kept_file_names_the_eleven_entries_once_each() -> None:
    entries = [(link.sso_code, link.ordinal) for link in get_hand_kept_act_links()]

    assert len(entries) == _HAND_KEPT_ENTRY_COUNT
    assert set(entries) == _HAND_KEPT_ENTRIES


def test_every_hand_kept_entry_lists_report_ids_once_and_gives_a_reason() -> None:
    for link in get_hand_kept_act_links():
        assert link.report_ids
        assert len(set(link.report_ids)) == len(link.report_ids)
        assert link.reason.endswith(".")


def test_the_bill_lookups_carry_no_dated_bills() -> None:
    assert [field.name for field in fields(BillLookups)] == [
        "title_key_to_linkable_bills",
        "loose_title_key_to_linkable_bills",
        "bill_number_to_linkable_bills",
    ]


def test_an_entry_titled_as_the_first_reading_links_to_the_bill_merged_with_a_misprinted_third_reading() -> None:
    report_rows = [
        ReportSittingDateTitleRow(
            1, datetime(1995, 5, 25), "REGULATION OF IMPORTS AND EXPORTS BILL"
        ),
        ReportSittingDateTitleRow(
            2, datetime(1995, 7, 7), "REGULATIONS OF IMPORTS AND EXPORTS BILL"
        ),
    ]
    grouping = group_bills(
        report_rows, frozenset({1}), frozenset({2}), [], [], report_rows, [], [], []
    )
    context = BillGroupingContext(
        grouping,
        {report_row.id: report_row.sitting_date.date() for report_row in report_rows},
        frozenset({1}),
        frozenset({2}),
        [],
        [],
    )

    bill_link = get_bill_link(
        "Regulation of Imports and Exports Act 1995",
        date(1995, 5, 25),
        None,
        date(1995, 7, 7),
        build_bill_lookups_from_context(context),
    )

    assert [bill_group.report_ids for bill_group in grouping.bill_groups] == [[1, 2]]
    assert bill_link == BillLink(0, BillLinkSource.FIRST_READING_DATE)
