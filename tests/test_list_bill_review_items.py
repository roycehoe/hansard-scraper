from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import Session

from database.act import Act, ActHistoryEntry
from database.acts_supplement import ActsSupplementCapture, ActsSupplementEntry
from database.bill import Bill, BillReport
from database.bills_supplement import BillsSupplementCapture, BillsSupplementEntry
from database.egazette_supplement import EgazetteSupplement
from enums import (
    ActHistoryEntryKind,
    ActNumberSource,
    BillEra,
    BillLinkSource,
    BillReviewItemKind,
    EgazetteSupplementKind,
    ReportType,
)
from schemas.bill_review_list import BillEraDoneTests
from scripts.list_bill_review_items import (
    get_bill_era,
    get_bill_review_list,
    get_summary_lines,
    get_supplement_bill_number_count,
)
from tests.bill_seed import seed_bill_report

_FIRST_READING_LINE = "Bill read a First time."
_THIRD_READING_LINE = "Bill read a Third time and passed."


def _seed_bill(
    session: Session,
    report_id: str,
    title: str,
    first_reading_date: datetime,
    third_reading_date: Optional[datetime],
) -> list[int]:
    report_ids = [
        seed_bill_report(
            session,
            f"{report_id}-first",
            ReportType.BILL_INTRODUCTION,
            first_reading_date,
            title,
            [_FIRST_READING_LINE],
        )
    ]
    if third_reading_date is not None:
        report_ids.append(
            seed_bill_report(
                session,
                f"{report_id}-third",
                ReportType.BILL,
                third_reading_date,
                title,
                [_THIRD_READING_LINE],
            )
        )
    return report_ids


def _seed_listing_entries(
    session: Session, entries: list[tuple[str, str, date]]
) -> None:
    capture = BillsSupplementCapture(
        original_url="https://sso.agc.gov.sg/Browse/Bills-Supp/Published/2024",
        archive_timestamp="20250109044700",
        capture_url="https://web.archive.org/web/20250109044700id_/https://sso.agc.gov.sg/Browse/Bills-Supp/Published/2024",
        content="<html></html>",
    )
    session.add(capture)
    session.flush()
    assert capture.id is not None
    session.add_all(
        BillsSupplementEntry(
            printed_title=printed_title,
            printed_number=f"Bill {bill_number.replace('/', ' of ')}",
            link=f"/Bills-Supp/{bill_number.replace('/', '-')}/Published/{publication_date:%Y%m%d}",
            bill_number=bill_number,
            publication_date=publication_date,
            capture_id=capture.id,
        )
        for printed_title, bill_number, publication_date in entries
    )
    session.commit()


def _seed_acts_listing_entries(
    session: Session, entries: list[tuple[str, str, date]]
) -> None:
    capture = ActsSupplementCapture(
        original_url="https://sso.agc.gov.sg/Browse/Acts-Supp/Published/2024",
        archive_timestamp="20250109044700",
        capture_url="https://web.archive.org/web/20250109044700id_/https://sso.agc.gov.sg/Browse/Acts-Supp/Published/2024",
        content="<html></html>",
    )
    session.add(capture)
    session.flush()
    assert capture.id is not None
    session.add_all(
        ActsSupplementEntry(
            printed_title=printed_title,
            printed_number=f"Act {act_number.replace('/', ' of ')}",
            link=f"/Acts-Supp/{act_number.replace('/', '-')}/Published/{publication_date:%Y%m%d}?DocDate={publication_date:%Y%m%d}",
            act_number=act_number,
            publication_date=publication_date,
            capture_id=capture.id,
        )
        for printed_title, act_number, publication_date in entries
    )
    session.commit()


def test_the_eras_split_at_1961_and_2006() -> None:
    assert get_bill_era(1955) == BillEra.YEARS_1955_TO_1960
    assert get_bill_era(1960) == BillEra.YEARS_1955_TO_1960
    assert get_bill_era(1961) == BillEra.YEARS_1961_TO_2005
    assert get_bill_era(2005) == BillEra.YEARS_1961_TO_2005
    assert get_bill_era(2006) == BillEra.YEARS_2006_ON


def test_the_bill_numbers_before_1966_count_by_series() -> None:
    bill_numbers = ["124/1961", "158/1961", "214/1963", "1/1963", "70/1965", "60/1966"]

    assert (
        get_supplement_bill_number_count(bill_numbers, BillEra.YEARS_1961_TO_2005)
        == 91 + 70 + 60
    )
    assert get_supplement_bill_number_count(bill_numbers, BillEra.YEARS_2006_ON) == 0


def test_the_supplement_items_and_the_done_tests(scratch_session: Session) -> None:
    _seed_bill(
        scratch_session,
        "alpha",
        "Alpha Bill",
        datetime(2024, 3, 4),
        datetime(2024, 4, 10),
    )
    beta_report_ids = _seed_bill(
        scratch_session, "beta", "Beta Bill", datetime(2024, 3, 11), None
    )
    _seed_bill(
        scratch_session,
        "gamma",
        "Gamma Bill",
        datetime(2024, 3, 18),
        datetime(2024, 4, 10),
    )
    road_report_ids = _seed_bill(
        scratch_session,
        "road",
        "Road Traffic (Amendment) Bill",
        datetime(2024, 6, 1),
        None,
    )
    epsilon_report_ids = _seed_bill(
        scratch_session,
        "epsilon",
        "Epsilon Bill",
        datetime(2024, 7, 1),
        datetime(2024, 8, 1),
    )
    _seed_listing_entries(
        scratch_session,
        [
            ("Alpha Bill", "10/2024", date(2024, 3, 5)),
            ("Beta Bill", "11/2024", date(2024, 5, 1)),
            ("Gamma Bill", "12/2024", date(2024, 3, 19)),
            ("Delta Bill", "13/2024", date(2023, 1, 15)),
            ("Road Traffic (Amendmeent) Bill", "14/2024", date(2024, 6, 3)),
        ],
    )

    review_list = get_bill_review_list(scratch_session, [], [])

    items_by_kind = {
        kind: [item for item in review_list.items if item.kind == kind]
        for kind in BillReviewItemKind
    }
    (beta_item,) = [
        item
        for item in items_by_kind[BillReviewItemKind.SUPPLEMENT_ENTRY_UNPLACED]
        if item.bill_number == "11/2024"
    ]
    assert beta_item.report_ids == beta_report_ids
    assert "R1b proposes the bill read on 2024-03-11" in beta_item.detail
    (delta_item,) = [
        item
        for item in items_by_kind[BillReviewItemKind.SUPPLEMENT_ENTRY_UNPLACED]
        if item.bill_number == "13/2024"
    ]
    assert delta_item.report_ids == []
    assert "no numbered neighbour on one side" in delta_item.detail
    (misprint_item,) = items_by_kind[BillReviewItemKind.MISPRINTED_PUBLICATION_DATE]
    assert misprint_item.bill_number == "13/2024"
    (loose_item,) = items_by_kind[
        BillReviewItemKind.SUPPLEMENT_LINK_BY_LOOSE_OR_SIMILAR_TITLE
    ]
    assert loose_item.bill_number == "14/2024"
    assert loose_item.report_ids == road_report_ids
    (passed_item,) = items_by_kind[
        BillReviewItemKind.PASSED_BILL_WITHOUT_SUPPLEMENT_ENTRY
    ]
    assert passed_item.report_ids == epsilon_report_ids
    assert items_by_kind[BillReviewItemKind.SUPPLEMENT_ENTRY_WITH_TWO_CANDIDATES] == []
    assert sorted(item.kind for item in review_list.items) == sorted(
        [
            BillReviewItemKind.SUPPLEMENT_ENTRY_UNPLACED,
            BillReviewItemKind.SUPPLEMENT_ENTRY_UNPLACED,
            BillReviewItemKind.MISPRINTED_PUBLICATION_DATE,
            BillReviewItemKind.SUPPLEMENT_LINK_BY_LOOSE_OR_SIMILAR_TITLE,
            BillReviewItemKind.PASSED_BILL_WITHOUT_SUPPLEMENT_ENTRY,
        ]
    )

    assert review_list.done_tests[-1] == BillEraDoneTests(
        era=BillEra.YEARS_2006_ON,
        hansard_bill_count=5,
        supplement_bill_number_count=14,
        numbered_bill_count=2,
        debate_complete_bill_count=2,
        passed_bill_count=3,
        outcome_resolved_bill_count=0,
        unclassed_passed_bill_count=3,
        unclassed_outcome_resolved_bill_count=0,
        review_item_count=5,
    )
    assert (
        "2006 on, test 1 bill completeness: 2 of 14 (14.3%) Supplement numbers held; 5 bills from Hansard"
        in get_summary_lines(review_list)
    )


def test_the_egazette_rows_count_in_the_done_tests(scratch_session: Session) -> None:
    alpha_report_ids = _seed_bill(
        scratch_session,
        "alpha",
        "Alpha Bill",
        datetime(2024, 3, 4),
        datetime(2024, 4, 10),
    )
    _seed_listing_entries(
        scratch_session, [("Alpha Bill", "10/2024", date(2024, 3, 5))]
    )
    stored_bill = Bill(
        title="Alpha Bill",
        title_key="alphabill",
        first_sitting_date=datetime(2024, 3, 4),
        last_sitting_date=datetime(2024, 4, 10),
        is_passed=True,
    )
    scratch_session.add(stored_bill)
    scratch_session.flush()
    assert stored_bill.id is not None
    scratch_session.add_all(
        BillReport(bill_id=stored_bill.id, report_id=report_id)
        for report_id in alpha_report_ids
    )
    scratch_session.add_all(
        [
            EgazetteSupplement(
                url="https://assets.egazette.gov.sg/2024/Legislative%20Supplements/Bills%20Supplement/12.pdf",
                year=2024,
                supplement_kind=EgazetteSupplementKind.BILLS,
                number=12,
                file_path="2024/bills/12.pdf",
                size_bytes=1,
                sha256="0" * 64,
                printed_title="Zeta Bill",
                printed_bill_number="12/2024",
                bill_number="12/2024",
                first_reading_date=date(2024, 5, 6),
                fetched_at=datetime(2026, 11, 8, tzinfo=timezone.utc),
            ),
            EgazetteSupplement(
                url="https://assets.egazette.gov.sg/2024/Legislative%20Supplements/Acts%20Supplement/09.pdf",
                year=2024,
                supplement_kind=EgazetteSupplementKind.ACTS,
                number=9,
                file_path="2024/acts/09.pdf",
                size_bytes=1,
                sha256="1" * 64,
                printed_title="Alpha Bill",
                printed_bill_number="10/2024",
                bill_number="10/2024",
                first_reading_date=date(2024, 3, 4),
                passing_date=date(2024, 4, 10),
                fetched_at=datetime(2026, 11, 8, tzinfo=timezone.utc),
                bill_link_source=BillLinkSource.BILL_NUMBER_PASSING_DATE,
                bill_id=stored_bill.id,
            ),
        ]
    )
    scratch_session.commit()

    review_list = get_bill_review_list(scratch_session, [], [])

    assert review_list.items == []
    assert review_list.done_tests[-1] == BillEraDoneTests(
        era=BillEra.YEARS_2006_ON,
        hansard_bill_count=1,
        supplement_bill_number_count=12,
        numbered_bill_count=1,
        debate_complete_bill_count=1,
        passed_bill_count=1,
        outcome_resolved_bill_count=1,
        unclassed_passed_bill_count=1,
        unclassed_outcome_resolved_bill_count=1,
        review_item_count=0,
    )


def test_two_same_title_bills_in_the_window_make_one_item(
    scratch_session: Session,
) -> None:
    _seed_bill(scratch_session, "one", "Twin Bill", datetime(2024, 3, 4), None)
    _seed_bill(scratch_session, "two", "Twin Bill", datetime(2024, 3, 6), None)
    _seed_listing_entries(scratch_session, [("Twin Bill", "10/2024", date(2024, 3, 7))])

    review_list = get_bill_review_list(scratch_session, [], [])

    (item,) = review_list.items
    assert item.kind == BillReviewItemKind.SUPPLEMENT_ENTRY_WITH_TWO_CANDIDATES
    assert item.bill_number == "10/2024"


def test_the_history_items_compare_the_stored_link_with_the_number_rule(
    scratch_session: Session,
) -> None:
    alpha_report_ids = _seed_bill(
        scratch_session,
        "alpha",
        "Alpha Bill",
        datetime(2024, 3, 4),
        datetime(2024, 4, 10),
    )
    _seed_listing_entries(
        scratch_session, [("Alpha Bill", "10/2024", date(2024, 3, 5))]
    )
    stored_bill = Bill(
        title="Alpha Bill",
        title_key="alphabill",
        first_sitting_date=datetime(2024, 3, 4),
        last_sitting_date=datetime(2024, 4, 10),
        is_passed=True,
    )
    act = Act(sso_code="AA2024", title="Alpha Act 2024")
    scratch_session.add_all([stored_bill, act])
    scratch_session.flush()
    assert stored_bill.id is not None
    assert act.id is not None
    scratch_session.add_all(
        BillReport(bill_id=stored_bill.id, report_id=report_id)
        for report_id in alpha_report_ids
    )
    scratch_session.add_all(
        [
            ActHistoryEntry(
                ordinal=1,
                printed_text="Act 5 of 2024",
                printed_law_number="Act 5 of 2024",
                printed_title="Alpha Act 2024",
                printed_bill_number="10/2024",
                first_reading_date=date(2024, 3, 4),
                third_reading_date=date(2024, 4, 10),
                kind=ActHistoryEntryKind.ACT,
                act_id=act.id,
            ),
            ActHistoryEntry(
                ordinal=2,
                printed_text="Act 9 of 2024",
                printed_law_number="Act 9 of 2024",
                printed_title="Alpha (Amendment) Act 2024",
                first_reading_date=date(2024, 8, 1),
                third_reading_date=date(2024, 9, 1),
                kind=ActHistoryEntryKind.ACT,
                bill_link_source=BillLinkSource.HAND_KEPT,
                act_id=act.id,
                bill_id=stored_bill.id,
            ),
        ]
    )
    scratch_session.commit()

    review_list = get_bill_review_list(scratch_session, [], [])

    assert [(item.kind, item.report_ids) for item in review_list.items] == [
        (BillReviewItemKind.HISTORY_LINK_BY_NUMBER_ONLY, alpha_report_ids),
        (
            BillReviewItemKind.HISTORY_LINK_WITHOUT_THIRD_READING_REPORT,
            alpha_report_ids,
        ),
    ]
    assert review_list.done_tests[-1] == BillEraDoneTests(
        era=BillEra.YEARS_2006_ON,
        hansard_bill_count=1,
        supplement_bill_number_count=10,
        numbered_bill_count=1,
        debate_complete_bill_count=1,
        passed_bill_count=1,
        outcome_resolved_bill_count=1,
        unclassed_passed_bill_count=1,
        unclassed_outcome_resolved_bill_count=1,
        review_item_count=2,
    )


def test_the_acts_supplement_items_and_the_act_number_in_test_3(
    scratch_session: Session,
) -> None:
    alpha_report_ids = _seed_bill(
        scratch_session,
        "alpha",
        "Alpha Bill",
        datetime(2024, 3, 4),
        datetime(2024, 4, 10),
    )
    twin_report_ids = _seed_bill(
        scratch_session,
        "twin",
        "Supplementary Supply (FY 2024) Bill",
        datetime(2024, 11, 4),
        datetime(2024, 12, 5),
    )
    _seed_acts_listing_entries(
        scratch_session,
        [
            ("Alpha Act 2024", "10/2024", date(2024, 5, 3)),
            ("Supplementary Supply (FY 2024) Act 2024", "42/2024", date(2024, 12, 31)),
            ("Supplementary Supply (FY 2024) Act 2025", "3/2025", date(2025, 2, 14)),
            ("Alpha (Amendment) Act 2024", "11/2024", date(2024, 9, 20)),
            ("Omega Act 2024", "12/2024", date(2024, 9, 20)),
        ],
    )
    stored_bill = Bill(
        title="Alpha Bill",
        title_key="alphabill",
        first_sitting_date=datetime(2024, 3, 4),
        last_sitting_date=datetime(2024, 4, 10),
        is_passed=True,
        act_number="10/2024",
        act_number_source=ActNumberSource.ACTS_SUPPLEMENT_LISTING,
    )
    scratch_session.add(stored_bill)
    scratch_session.flush()
    assert stored_bill.id is not None
    scratch_session.add_all(
        BillReport(bill_id=stored_bill.id, report_id=report_id)
        for report_id in alpha_report_ids
    )
    scratch_session.commit()

    review_list = get_bill_review_list(scratch_session, [], [])

    assert [
        (item.kind, item.report_ids, item.detail)
        for item in review_list.items
        if item.kind != BillReviewItemKind.PASSED_BILL_WITHOUT_SUPPLEMENT_ENTRY
    ] == [
        (
            BillReviewItemKind.ACTS_SUPPLEMENT_BILL_WITH_TWO_ACT_NUMBERS,
            twin_report_ids,
            "Last debated 2024-12-05; Acts Supplement entries of the title within the window: 3/2025, 42/2024",
        ),
        (
            BillReviewItemKind.ACTS_SUPPLEMENT_ENTRY_UNPLACED,
            twin_report_ids,
            "Act 42/2024 published 2024-12-31; the nearest passed bill of this title was last debated 2024-12-05, 26 days before",
        ),
        (
            BillReviewItemKind.ACTS_SUPPLEMENT_ENTRY_UNPLACED,
            twin_report_ids,
            "Act 3/2025 published 2025-02-14; the nearest passed bill of this title was last debated 2024-12-05, 71 days before",
        ),
        (
            BillReviewItemKind.ACTS_SUPPLEMENT_ENTRY_UNPLACED,
            [],
            "Act 11/2024 published 2024-09-20; no passed bill of this title",
        ),
        (
            BillReviewItemKind.ACTS_SUPPLEMENT_ENTRY_UNPLACED,
            [],
            "Act 12/2024 published 2024-09-20; no passed bill of this title",
        ),
    ]
    assert review_list.done_tests[-1] == BillEraDoneTests(
        era=BillEra.YEARS_2006_ON,
        hansard_bill_count=2,
        supplement_bill_number_count=0,
        numbered_bill_count=0,
        debate_complete_bill_count=0,
        passed_bill_count=2,
        outcome_resolved_bill_count=2,
        unclassed_passed_bill_count=1,
        unclassed_outcome_resolved_bill_count=1,
        review_item_count=7,
    )
    assert (
        "2006 on, test 3 outcome resolved: 2 of 2 (100.0%) passed bills link to an Act or an Act number or carry a class; 1 of 1 (100.0%) passed bills of no class link to an Act or an Act number"
        in get_summary_lines(review_list)
    )
