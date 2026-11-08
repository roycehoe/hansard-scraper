from datetime import date, datetime

import pytest

from crud.report import ReportSittingDateTitleRow
from enums import ActNumberSource, BillClass, BillNumberSource, RepealedActUrlSource
from exceptions import HansardHandKeptEntryError
from schemas.hand_kept_bill import HandKeptBill
from services.bill import (
    ActNumberCandidate,
    BillGroup,
    BillGrouping,
    BillNumberCandidate,
    RepealedActCandidate,
    build_acts_supplement_act_number_candidate,
    build_egazette_bill_number_candidate,
    build_listing_bill_number_candidate,
    build_repealed_acts_listing_candidate,
    get_bill_class,
    group_bills,
    is_publication_date_misprinted,
)


def _row(
    report_id: int, sitting_date: datetime, title: str
) -> ReportSittingDateTitleRow:
    return ReportSittingDateTitleRow(report_id, sitting_date, title)


def _group(
    report_rows: list[ReportSittingDateTitleRow],
    first_reading_report_ids: set[int],
    third_reading_report_ids: set[int],
    bill_number_candidates: list[BillNumberCandidate] = [],
    hand_kept_bills: list[HandKeptBill] = [],
    act_number_candidates: list[ActNumberCandidate] = [],
    repealed_act_candidates: list[RepealedActCandidate] = [],
) -> BillGrouping:
    return group_bills(
        report_rows,
        frozenset(first_reading_report_ids),
        frozenset(third_reading_report_ids),
        [],
        hand_kept_bills,
        report_rows,
        bill_number_candidates,
        act_number_candidates,
        repealed_act_candidates,
    )


def _report_ids(grouping: BillGrouping) -> list[list[int]]:
    return [bill_group.report_ids for bill_group in grouping.bill_groups]


def _one(grouping: BillGrouping) -> BillGroup:
    (bill_group,) = grouping.bill_groups
    return bill_group


def test_supply_and_repeal_titles_take_a_class_and_other_titles_take_none() -> None:
    assert get_bill_class("supplybill") == BillClass.SUPPLY
    assert get_bill_class("supplementarysupplyfy2020bill") == BillClass.SUPPLY
    assert get_bill_class("appropriationbill") == BillClass.SUPPLY
    assert get_bill_class("thesecondsupplementarysupplyno2bill") == BillClass.SUPPLY
    assert (
        get_bill_class("rehabilitationloanappropriationrepealbill") == BillClass.REPEAL
    )
    assert get_bill_class("supplyofgoodsamendmentbill") is None
    assert get_bill_class("liquorcontrolsupplyandconsumptionbill") is None
    assert (
        get_bill_class("restrictionsonthesupplyofpetroleumandelectricitybill") is None
    )
    assert get_bill_class("statutesrepealamendmentbill") is None


def test_listing_candidate_window_follows_the_publication_year() -> None:
    assert build_listing_bill_number_candidate(
        "Banking Ordinance", "148/1961", date(1961, 6, 26)
    ) == BillNumberCandidate(
        "148/1961",
        "bankingbill",
        BillNumberSource.BILLS_SUPPLEMENT_LISTING,
        date(1961, 5, 22),
        date(1961, 6, 26),
    )
    assert build_listing_bill_number_candidate(
        "Supply Bill", "4/2026", date(2026, 2, 24)
    ).earliest_first_reading_date == date(2026, 2, 20)
    assert build_listing_bill_number_candidate(
        "Supply Bill", "1/1990", date(1990, 3, 10)
    ).earliest_first_reading_date == date(1990, 3, 1)
    assert build_listing_bill_number_candidate(
        "Supply Bill", "1/1970", date(1970, 3, 20)
    ).earliest_first_reading_date == date(1970, 3, 2)


def test_egazette_candidate_window_is_a_day_either_side_of_the_first_reading() -> None:
    assert build_egazette_bill_number_candidate(
        "Enlistment and Other Matters (Amendment) Bill", "1/2024", date(2024, 1, 9)
    ) == BillNumberCandidate(
        "1/2024",
        "enlistmentandothermattersamendmentbill",
        BillNumberSource.EGAZETTE_BILLS_SUPPLEMENT,
        date(2024, 1, 8),
        date(2024, 1, 10),
    )


_MONEYLENDERS_ROWS = [
    _row(1, datetime(2005, 10, 17), "MONEYLENDERS (AMENDMENT) BILL"),
    _row(2, datetime(2005, 11, 21), "MONEYLENDERS (AMENDMENT) BILL"),
]


def test_a_listing_entry_numbers_the_bill_read_a_first_time_in_its_window() -> None:
    grouping = _group(
        _MONEYLENDERS_ROWS,
        {1},
        {2},
        [
            build_listing_bill_number_candidate(
                "Moneylenders (Amendment) Bill", "30/2005", date(2005, 10, 18)
            )
        ],
    )

    bill_group = _one(grouping)
    assert bill_group.bill_number == "30/2005"
    assert bill_group.bill_number_source == BillNumberSource.BILLS_SUPPLEMENT_LISTING
    assert bill_group.bill_class is None


def test_an_entry_published_before_the_first_reading_numbers_nothing() -> None:
    grouping = _group(
        _MONEYLENDERS_ROWS,
        {1},
        {2},
        [
            build_listing_bill_number_candidate(
                "Moneylenders (Amendment) Bill", "30/2005", date(2005, 10, 16)
            )
        ],
    )

    assert _one(grouping).bill_number is None


def test_an_entry_published_after_the_window_numbers_nothing() -> None:
    grouping = _group(
        _MONEYLENDERS_ROWS,
        {1},
        {2},
        [
            build_listing_bill_number_candidate(
                "Moneylenders (Amendment) Bill", "30/2005", date(2005, 10, 27)
            )
        ],
    )

    assert _one(grouping).bill_number is None


def test_a_bill_matched_by_two_numbers_gets_none() -> None:
    grouping = _group(
        _MONEYLENDERS_ROWS,
        {1},
        {2},
        [
            build_listing_bill_number_candidate(
                "Moneylenders (Amendment) Bill", "30/2005", date(2005, 10, 18)
            ),
            build_listing_bill_number_candidate(
                "Moneylenders (Amendment) Bill", "31/2005", date(2005, 10, 18)
            ),
        ],
    )

    assert _one(grouping).bill_number is None


def test_a_number_matching_two_bills_numbers_neither() -> None:
    grouping = _group(
        [
            _row(1, datetime(1973, 3, 2), "ROAD TRAFFIC (AMENDMENT) BILL"),
            _row(2, datetime(1973, 3, 9), "ROAD TRAFFIC (AMENDMENT) BILL"),
        ],
        {1, 2},
        set(),
        [
            build_listing_bill_number_candidate(
                "Road Traffic (Amendment) Bill", "34/1973", date(1973, 3, 10)
            )
        ],
    )

    assert [bill_group.bill_number for bill_group in grouping.bill_groups] == [
        None,
        None,
    ]


def test_an_egazette_number_fills_a_bill_the_listing_lacks() -> None:
    grouping = _group(
        [
            _row(1, datetime(2024, 9, 9), "Some Matters Bill"),
            _row(2, datetime(2024, 10, 14), "Some Matters Bill"),
        ],
        {1},
        {2},
        [
            build_egazette_bill_number_candidate(
                "Some Matters Bill", "36/2024", date(2024, 9, 9)
            )
        ],
    )

    bill_group = _one(grouping)
    assert bill_group.bill_number == "36/2024"
    assert bill_group.bill_number_source == BillNumberSource.EGAZETTE_BILLS_SUPPLEMENT


def test_the_listing_is_the_source_when_both_sources_give_the_same_number() -> None:
    grouping = _group(
        [
            _row(1, datetime(2024, 9, 9), "Some Matters Bill"),
            _row(2, datetime(2024, 10, 14), "Some Matters Bill"),
        ],
        {1},
        {2},
        [
            build_egazette_bill_number_candidate(
                "Some Matters Bill", "36/2024", date(2024, 9, 9)
            ),
            build_listing_bill_number_candidate(
                "Some Matters Bill", "36/2024", date(2024, 9, 9)
            ),
        ],
    )

    assert (
        _one(grouping).bill_number_source == BillNumberSource.BILLS_SUPPLEMENT_LISTING
    )


def test_an_entry_title_matches_a_hansard_title_that_keeps_the_leading_the() -> None:
    grouping = _group(
        [
            _row(1, datetime(1965, 6, 1), "THE SOCIETY OF SAINT MAUR BILL"),
            _row(2, datetime(1965, 7, 1), "THE SOCIETY OF SAINT MAUR BILL"),
        ],
        {1},
        {2},
        [
            build_listing_bill_number_candidate(
                "The Society of Saint Maur Bill", "20/1965", date(1965, 6, 3)
            )
        ],
    )

    assert _one(grouping).bill_number == "20/1965"


def test_a_supply_bill_takes_the_supply_class() -> None:
    grouping = _group(
        [_row(1, datetime(2026, 2, 24), "Supply Bill")],
        {1},
        {1},
    )

    assert _one(grouping).bill_class == BillClass.SUPPLY


_CONSTITUTION_1987_ROWS = [
    _row(
        1,
        datetime(1987, 7, 28),
        "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT) BILL",
    ),
    _row(
        2,
        datetime(1987, 8, 31),
        "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT) BILL",
    ),
    _row(
        3,
        datetime(1987, 11, 30),
        "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT NO. 2) BILL",
    ),
    _row(
        4,
        datetime(1988, 1, 12),
        "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT NO. 2) BILL",
    ),
    _row(
        5,
        datetime(1988, 5, 18),
        "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT) BILL",
    ),
]
_CONSTITUTION_1987_CANDIDATE = build_listing_bill_number_candidate(
    "Constitution of the Republic of Singapore (Amendment No. 2) Bill",
    "24/1987",
    date(1987, 12, 1),
)


def test_a_bill_renamed_in_committee_is_one_bill_under_its_last_title() -> None:
    grouping = _group(
        _CONSTITUTION_1987_ROWS, {1, 3}, {2, 5}, [_CONSTITUTION_1987_CANDIDATE]
    )

    assert _report_ids(grouping) == [[1, 2], [3, 4, 5]]
    renamed_bill = grouping.bill_groups[1]
    assert (
        renamed_bill.title
        == "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT) BILL"
    )
    assert renamed_bill.first_sitting_date == datetime(1987, 11, 30)
    assert renamed_bill.last_sitting_date == datetime(1988, 5, 18)
    assert renamed_bill.is_passed
    assert renamed_bill.bill_number == "24/1987"
    assert [
        (split_merge.head_report_ids, split_merge.tail_report_ids)
        for split_merge in grouping.split_merges
    ] == [([3, 4], [5])]


def test_the_1989_constitution_bill_merges_past_a_later_complete_bill_of_the_head_title() -> (
    None
):
    grouping = _group(
        [
            _row(
                1,
                datetime(1989, 10, 6),
                "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT NO. 2) BILL",
            ),
            _row(
                2,
                datetime(1989, 11, 29),
                "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT NO. 2) BILL",
            ),
            _row(
                3,
                datetime(1989, 11, 30),
                "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT NO. 2) BILL",
            ),
            _row(
                4,
                datetime(1990, 3, 2),
                "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT NO. 2) BILL",
            ),
            _row(
                5,
                datetime(1990, 3, 29),
                "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT NO. 2) BILL",
            ),
            _row(
                6,
                datetime(1990, 3, 29),
                "CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT) BILL",
            ),
        ],
        {1, 4},
        {5, 6},
    )

    assert _report_ids(grouping) == [[1, 2, 3, 6], [4, 5]]


def test_a_select_committee_bill_split_by_the_year_rule_is_merged_back() -> None:
    grouping = _group(
        [
            _row(1, datetime(1994, 5, 23), "MAINTENANCE OF PARENTS BILL"),
            _row(2, datetime(1994, 7, 25), "MAINTENANCE OF PARENTS BILL"),
            _row(3, datetime(1994, 7, 26), "MAINTENANCE OF PARENTS BILL"),
            _row(4, datetime(1994, 7, 27), "MAINTENANCE OF PARENTS BILL"),
            _row(5, datetime(1995, 11, 2), "MAINTENANCE OF PARENTS BILL"),
        ],
        {1},
        {5},
    )

    assert _report_ids(grouping) == [[1, 2, 3, 4, 5]]
    assert _one(grouping).is_passed


def test_a_bill_whose_committee_added_a_word_to_the_title_is_merged() -> None:
    grouping = _group(
        [
            _row(1, datetime(2004, 2, 6), "BUILDING MAINTENANCE AND MANAGEMENT BILL"),
            _row(2, datetime(2004, 4, 19), "BUILDING MAINTENANCE AND MANAGEMENT BILL"),
            _row(
                3,
                datetime(2004, 10, 19),
                "BUILDING MAINTENANCE AND STRATA MANAGEMENT BILL",
            ),
        ],
        {1},
        {3},
    )

    assert _report_ids(grouping) == [[1, 2, 3]]
    assert _one(grouping).title == "BUILDING MAINTENANCE AND STRATA MANAGEMENT BILL"


@pytest.mark.parametrize(
    ("head_title", "tail_title", "head_date", "tail_date"),
    [
        (
            "STATUTES (MISCELLANEOUS AMENDMENTS) (AMENDMENT NO. 2) BILL",
            "STATUTES (MISCELLANEOUS AMENDMENTS) (NO. 2) BILL",
            datetime(2005, 10, 17),
            datetime(2005, 11, 21),
        ),
        (
            "Goods and Services Tax (Amendment) Bill",
            "Good and Services Tax (Amendment) Bill",
            datetime(2019, 10, 7),
            datetime(2019, 11, 4),
        ),
        (
            "BOTANICAL GARDENS BILL",
            "BOTANIC GARDENS BILL",
            datetime(1957, 8, 21),
            datetime(1957, 9, 11),
        ),
        (
            "EVIDENCE (AMENDMEND)BILL",
            "EVIDENCE (AMENDMENT) BILL",
            datetime(1975, 7, 29),
            datetime(1975, 8, 19),
        ),
        (
            "MINOR OFFENCES (AMENDMENI) BILL",
            "MINOR OFFENCES (AMENDMENT) BILL",
            datetime(1967, 10, 31),
            datetime(1967, 11, 14),
        ),
    ],
)
def test_a_misspelt_first_reading_title_is_merged_with_its_later_readings(
    head_title: str, tail_title: str, head_date: datetime, tail_date: datetime
) -> None:
    grouping = _group(
        [_row(1, head_date, head_title), _row(2, tail_date, tail_title)], {1}, {2}
    )

    assert _report_ids(grouping) == [[1, 2]]
    assert _one(grouping).title == tail_title


def test_a_long_title_cut_to_a_short_one_is_not_merged() -> None:
    grouping = _group(
        [
            _row(
                1,
                datetime(1958, 8, 13),
                "REVEREND MOTHER SUPERIOR OF THE CONGREGATION OF GOOD SHEPHERD NUNS IN MALAYA BILL",
            ),
            _row(2, datetime(1958, 9, 10), "GOOD SHEPHERD NUNS BILL"),
            _row(3, datetime(1958, 11, 5), "GOOD SHEPHERD NUNS BILL"),
        ],
        {1},
        {3},
    )

    assert _report_ids(grouping) == [[1], [2, 3]]


_HOUSING_ROWS = [
    _row(1, datetime(1962, 6, 27), "HOUSING AND DEVELOPMENT (AMENDMENT) BILL"),
    _row(2, datetime(1962, 7, 9), "HOUSING AND DEVELOPMENT (AMENDMENT) BILL"),
    _row(3, datetime(1963, 11, 28), "HOUSING AND DEVELOPMENT (AMENDMENT NO. 2) BILL"),
    _row(4, datetime(1963, 12, 20), "HOUSING AND DEVELOPMENT (AMENDMENT NO. 2) BILL"),
]


def test_two_bills_the_listing_numbers_differently_are_not_merged() -> None:
    grouping = _group(
        _HOUSING_ROWS,
        {1},
        {4},
        [
            build_listing_bill_number_candidate(
                "Housing and Development (Amendment) Ordinance",
                "183/1962",
                date(1962, 6, 27),
            ),
            build_listing_bill_number_candidate(
                "Housing and Development (Amendment No. 2) Ordinance",
                "12/1963",
                date(1963, 11, 29),
            ),
        ],
    )

    assert _report_ids(grouping) == [[1, 2], [3, 4]]
    assert [bill_group.bill_number for bill_group in grouping.bill_groups] == [
        "183/1962",
        None,
    ]


def test_a_tail_read_after_its_own_listing_window_is_not_merged() -> None:
    grouping = _group(
        [
            _row(1, datetime(2000, 5, 8), "ROADS (AMENDMENT) BILL"),
            _row(2, datetime(2001, 3, 20), "ROADS (AMENDMENT NO. 2) BILL"),
            _row(3, datetime(2001, 4, 10), "ROADS (AMENDMENT NO. 2) BILL"),
        ],
        {1},
        {3},
        [
            build_listing_bill_number_candidate(
                "Roads (Amendment) Bill", "10/2000", date(2000, 5, 9)
            ),
            build_listing_bill_number_candidate(
                "Roads (Amendment No. 2) Bill", "15/2001", date(2001, 2, 4)
            ),
        ],
    )

    assert _report_ids(grouping) == [[1], [2, 3]]
    assert [bill_group.bill_number for bill_group in grouping.bill_groups] == [
        "10/2000",
        None,
    ]


def test_a_misprinted_publication_date_is_flagged_and_an_in_year_date_is_not() -> None:
    assert is_publication_date_misprinted("16/2007", date(2004, 4, 10))
    assert is_publication_date_misprinted("54/1970", date(1971, 12, 5))
    assert not is_publication_date_misprinted("54/1970", date(1971, 1, 31))
    assert not is_publication_date_misprinted("1/2024", date(2024, 1, 2))


def test_the_same_two_bills_merge_when_no_listing_tells_them_apart() -> None:
    grouping = _group(_HOUSING_ROWS, {1}, {4})

    assert _report_ids(grouping) == [[1, 2, 3, 4]]


def test_a_tail_two_heads_claim_is_merged_with_neither() -> None:
    grouping = _group(
        [
            _row(1, datetime(1990, 1, 10), "ROADS (AMENDMENT) BILL"),
            _row(2, datetime(1990, 3, 10), "ROADS (AMENDMENT NO. 2) BILL"),
            _row(3, datetime(1990, 6, 10), "ROADS (AMENDMENT NO. 3) BILL"),
        ],
        {1, 2},
        {3},
    )

    assert _report_ids(grouping) == [[1], [2], [3]]


def test_a_head_more_than_800_days_before_the_tail_is_not_merged() -> None:
    grouping = _group(
        [
            _row(1, datetime(1990, 1, 10), "ROADS (AMENDMENT) BILL"),
            _row(2, datetime(1992, 6, 10), "ROADS (AMENDMENT) BILL"),
        ],
        {1},
        {2},
    )

    assert _report_ids(grouping) == [[1], [2]]
    assert grouping.split_merges == []


def test_a_hand_kept_bill_equal_to_a_merge_stays_one_bill() -> None:
    grouping = _group(
        _CONSTITUTION_1987_ROWS,
        {1, 3},
        {2, 5},
        [_CONSTITUTION_1987_CANDIDATE],
        [
            HandKeptBill(
                title="CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT) BILL",
                report_ids=[5, 4, 3],
                reason="renamed in committee",
            )
        ],
    )

    assert _report_ids(grouping) == [[1, 2], [3, 4, 5]]
    assert grouping.bill_groups[1].bill_number == "24/1987"


def test_a_hand_kept_bill_that_splits_a_merge_is_refused() -> None:
    with pytest.raises(HansardHandKeptEntryError):
        _group(
            _CONSTITUTION_1987_ROWS,
            {1, 3},
            {2, 5},
            [_CONSTITUTION_1987_CANDIDATE],
            [
                HandKeptBill(
                    title="CONSTITUTION OF THE REPUBLIC OF SINGAPORE (AMENDMENT) BILL",
                    report_ids=[4, 5],
                    reason="wrong",
                )
            ],
        )


def _act_number_candidate(
    printed_title: str, act_number: str, publication_date: date
) -> ActNumberCandidate:
    return build_acts_supplement_act_number_candidate(
        printed_title, act_number, publication_date
    )


def test_a_passed_bill_takes_the_act_number_published_after_its_third_reading() -> None:
    grouping = _group(
        [
            _row(1, datetime(2010, 10, 18), "MAINTENANCE OF PARENTS (AMENDMENT) BILL"),
            _row(2, datetime(2010, 11, 23), "MAINTENANCE OF PARENTS (AMENDMENT) BILL"),
        ],
        {1},
        {2},
        act_number_candidates=[
            _act_number_candidate(
                "Maintenance of Parents (Amendment) Act 2010",
                "37/2010",
                date(2011, 1, 3),
            )
        ],
    )

    assert _one(grouping).act_number == "37/2010"
    assert _one(grouping).act_number_source == ActNumberSource.ACTS_SUPPLEMENT_LISTING


def test_the_act_number_window_runs_from_a_day_before_to_120_days_after() -> None:
    report_rows = [_row(1, datetime(2010, 11, 23), "ALPHA BILL")]
    candidate_a_day_before = _act_number_candidate(
        "Alpha Act 2010", "1/2010", date(2010, 11, 22)
    )
    candidate_two_days_before = _act_number_candidate(
        "Alpha Act 2010", "2/2010", date(2010, 11, 21)
    )
    candidate_120_days_after = _act_number_candidate(
        "Alpha Act 2011", "3/2011", date(2011, 3, 23)
    )
    candidate_121_days_after = _act_number_candidate(
        "Alpha Act 2011", "4/2011", date(2011, 3, 24)
    )

    assert (
        _one(
            _group(
                report_rows, set(), {1}, act_number_candidates=[candidate_a_day_before]
            )
        ).act_number
        == "1/2010"
    )
    assert (
        _one(
            _group(
                report_rows,
                set(),
                {1},
                act_number_candidates=[candidate_two_days_before],
            )
        ).act_number
        is None
    )
    assert (
        _one(
            _group(
                report_rows,
                set(),
                {1},
                act_number_candidates=[candidate_120_days_after],
            )
        ).act_number
        == "3/2011"
    )
    assert (
        _one(
            _group(
                report_rows,
                set(),
                {1},
                act_number_candidates=[candidate_121_days_after],
            )
        ).act_number
        is None
    )


def test_two_act_numbers_of_the_title_in_the_window_give_no_act_number() -> None:
    grouping = _group(
        [_row(1, datetime(2002, 12, 5), "SUPPLEMENTARY SUPPLY (FY 2002) BILL")],
        set(),
        {1},
        act_number_candidates=[
            _act_number_candidate(
                "Supplementary Supply (FY 2002) Act 2002", "42/2002", date(2002, 12, 31)
            ),
            _act_number_candidate(
                "Supplementary Supply (FY 2002) Act 2003", "3/2003", date(2003, 2, 14)
            ),
        ],
    )

    assert _one(grouping).act_number is None
    assert _one(grouping).act_number_source is None


def test_one_act_number_listed_twice_in_the_window_is_taken() -> None:
    grouping = _group(
        [_row(1, datetime(2018, 11, 20), "ALPHA BILL")],
        set(),
        {1},
        act_number_candidates=[
            _act_number_candidate("Alpha Act 2018", "53/2018", date(2018, 12, 21)),
            _act_number_candidate("Alpha Act 2018", "53/2018", date(2019, 1, 11)),
        ],
    )

    assert _one(grouping).act_number == "53/2018"


def test_a_bill_not_passed_and_a_bill_of_another_title_take_no_act_number() -> None:
    candidates = [_act_number_candidate("Alpha Act 2010", "1/2010", date(2010, 12, 1))]

    assert (
        _one(
            _group(
                [_row(1, datetime(2010, 11, 23), "ALPHA BILL")],
                {1},
                set(),
                act_number_candidates=candidates,
            )
        ).act_number
        is None
    )
    assert (
        _one(
            _group(
                [_row(1, datetime(2010, 11, 23), "BETA BILL")],
                set(),
                {1},
                act_number_candidates=candidates,
            )
        ).act_number
        is None
    )


def _repealed_act_candidate(
    printed_title: str, sso_code: str, enactment_year: int, repeal_date: date
) -> RepealedActCandidate:
    return build_repealed_acts_listing_candidate(
        printed_title,
        sso_code,
        enactment_year,
        repeal_date,
        f"/Act/{sso_code}/Repealed/{repeal_date:%Y%m%d}?DocDate={repeal_date:%Y%m%d}",
    )


def test_a_principal_bill_takes_the_act_enacted_in_its_first_or_last_report_year() -> (
    None
):
    grouping = _group(
        [
            _row(1, datetime(1986, 3, 25), "COPYRIGHT BILL"),
            _row(2, datetime(1987, 1, 20), "COPYRIGHT BILL"),
        ],
        {1},
        {2},
        repealed_act_candidates=[
            _repealed_act_candidate(
                "Copyright Act (Repealed)", "CA1914", 1914, date(1987, 4, 10)
            ),
            _repealed_act_candidate(
                "Copyright Act (Repealed)", "CA1987", 1987, date(2021, 11, 21)
            ),
        ],
    )

    assert _one(grouping).repealed_act_url == (
        "https://sso.agc.gov.sg/Act/CA1987/Repealed/20211121?DocDate=20211121"
    )
    assert (
        _one(grouping).repealed_act_url_source
        == RepealedActUrlSource.REPEALED_ACTS_LISTING
    )


def test_an_amendment_bill_takes_the_act_alive_through_its_dates() -> None:
    grouping = _group(
        [
            _row(1, datetime(1980, 3, 25), "ACCOUNTANTS (AMENDMENT) BILL"),
            _row(2, datetime(1980, 4, 20), "ACCOUNTANTS (AMENDMENT) BILL"),
        ],
        {1},
        {2},
        repealed_act_candidates=[
            _repealed_act_candidate(
                "Accountants Act (Repealed)", "AA1963", 1963, date(1989, 2, 11)
            ),
            _repealed_act_candidate(
                "Accountants Act (Repealed)", "AA1987", 1987, date(2020, 1, 1)
            ),
        ],
    )

    assert _one(grouping).repealed_act_url == (
        "https://sso.agc.gov.sg/Act/AA1963/Repealed/19890211?DocDate=19890211"
    )


def test_two_acts_alive_through_an_amendment_bill_give_no_repealed_act_link() -> None:
    grouping = _group(
        [
            _row(1, datetime(1988, 3, 25), "ACCOUNTANTS (AMENDMENT) BILL"),
            _row(2, datetime(1988, 4, 20), "ACCOUNTANTS (AMENDMENT) BILL"),
        ],
        {1},
        {2},
        repealed_act_candidates=[
            _repealed_act_candidate(
                "Accountants Act (Repealed)", "AA1963", 1963, date(2000, 1, 1)
            ),
            _repealed_act_candidate(
                "Accountants Act (Repealed)", "AA1987", 1987, date(2020, 1, 1)
            ),
        ],
    )

    assert _one(grouping).repealed_act_url is None
    assert _one(grouping).repealed_act_url_source is None


def test_status_words_and_a_title_year_are_stripped_from_the_listing_title() -> None:
    grouping = _group(
        [_row(1, datetime(1994, 2, 10), "SUPPLY BILL")],
        set(),
        {1},
        repealed_act_candidates=[
            _repealed_act_candidate(
                "Supply Act 1994 (Expired) (Spent)", "SA1994", 1994, date(1995, 4, 1)
            ),
        ],
    )

    assert _one(grouping).repealed_act_url == (
        "https://sso.agc.gov.sg/Act/SA1994/Repealed/19950401?DocDate=19950401"
    )


def test_a_bill_not_passed_and_a_bill_of_another_title_take_no_repealed_act_link() -> (
    None
):
    candidates = [
        _repealed_act_candidate(
            "Alpha Act (Repealed)", "AA1987", 1987, date(2020, 1, 1)
        )
    ]

    assert (
        _one(
            _group(
                [_row(1, datetime(1987, 3, 25), "ALPHA BILL")],
                {1},
                set(),
                repealed_act_candidates=candidates,
            )
        ).repealed_act_url
        is None
    )
    assert (
        _one(
            _group(
                [_row(1, datetime(1987, 3, 25), "BETA BILL")],
                set(),
                {1},
                repealed_act_candidates=candidates,
            )
        ).repealed_act_url
        is None
    )


def test_one_sso_code_listed_twice_is_one_repealed_act_candidate() -> None:
    grouping = _group(
        [_row(1, datetime(1987, 3, 25), "ALPHA BILL")],
        set(),
        {1},
        repealed_act_candidates=[
            _repealed_act_candidate(
                "Alpha Act (Repealed)", "AA1987", 1987, date(2020, 1, 1)
            ),
            _repealed_act_candidate(
                "Alpha Act (Repealed)", "AA1987", 1987, date(2020, 1, 1)
            ),
        ],
    )

    assert _one(grouping).repealed_act_url is not None
