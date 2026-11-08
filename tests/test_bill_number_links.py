import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlmodel import Session

from crud.egazette_supplement import CRUDEgazetteSupplement
from database.bills_supplement import BillsSupplementCapture, BillsSupplementEntry
from database.egazette_supplement import EgazetteSupplement
from enums import BillLinkSource, BillNumberSource, EgazetteSupplementKind, ReportType
from populate.act_links import (
    get_act_link_plan,
    get_act_link_write,
    write_act_link_plan,
)
from services.act_link import (
    LinkableBill,
    build_bill_lookups,
    get_bill_number_link_index,
)
from services.act_link_write import get_first_difference
from tests.bill_seed import seed_bill_report

_FIRST_READING_DATE = datetime(2024, 11, 12)
_PASSING_DATE = datetime(2025, 1, 8)
_FOOD_SAFETY_TITLE = "Food Safety and Security Bill"
_FOOD_SAFETY_ACT_TEXT = """\
LEGISLATIVE HISTORY
 1. Act 3 of 2025 — Food Safety and Security Act 2025
     Bill                             :   49/2024
     First Reading                    :   12 November 2024
     Second and Third Readings        :   8 January 2025
     Commencement                     :   1 March 2025
Abbreviations
"""
_RENAMED_ACT_TEXT = """\
LEGISLATIVE HISTORY
 1. Act 3 of 2025 — Food Supply Chain Act 2025
     Bill                             :   49/2024
     First Reading                    :   12 November 2024
     Second and Third Readings        :   8 January 2025
     Commencement                     :   1 March 2025
Abbreviations
"""
_BILLS_URL = "https://assets.egazette.gov.sg/2024/Legislative%20Supplements/Bills%20Supplement/49.pdf"
_ACTS_URL = "https://assets.egazette.gov.sg/2025/Legislative%20Supplements/Acts%20Supplement/01.pdf"

_NUMBERED_BILLS = build_bill_lookups(
    {
        "roadtrafficamendmentbill": [
            LinkableBill(0, [date(1970, 3, 2), date(1970, 4, 1)])
        ]
    },
    {
        "29/1970": [LinkableBill(0, [date(1970, 3, 2), date(1970, 4, 1)])],
        "30/1970": [
            LinkableBill(1, [date(1970, 3, 2)]),
            LinkableBill(2, [date(1970, 3, 3)]),
        ],
    },
)


def test_a_printed_bill_number_links_the_bill_read_within_a_day() -> None:
    assert get_bill_number_link_index("29/70", date(1970, 3, 3), _NUMBERED_BILLS) == 0
    assert get_bill_number_link_index("29/1970", date(1970, 3, 2), _NUMBERED_BILLS) == 0


def test_a_printed_bill_number_links_nothing_when_the_dates_disagree() -> None:
    assert (
        get_bill_number_link_index("29/1970", date(1970, 3, 5), _NUMBERED_BILLS) is None
    )


def test_a_printed_bill_number_two_bills_share_links_neither() -> None:
    assert (
        get_bill_number_link_index("30/1970", date(1970, 3, 2), _NUMBERED_BILLS) is None
    )


def test_a_missing_or_unknown_bill_number_links_nothing() -> None:
    assert get_bill_number_link_index(None, date(1970, 3, 2), _NUMBERED_BILLS) is None
    assert get_bill_number_link_index("29/1970", None, _NUMBERED_BILLS) is None
    assert (
        get_bill_number_link_index("31/1970", date(1970, 3, 2), _NUMBERED_BILLS) is None
    )
    assert (
        get_bill_number_link_index("G.N. 31", date(1970, 3, 2), _NUMBERED_BILLS) is None
    )


def _seed_food_safety_reports(session: Session) -> list[int]:
    return [
        seed_bill_report(
            session,
            "food-first",
            ReportType.BILL_INTRODUCTION,
            _FIRST_READING_DATE,
            _FOOD_SAFETY_TITLE,
            ["Bill read a First time."],
        ),
        seed_bill_report(
            session,
            "food-third",
            ReportType.BILL,
            _PASSING_DATE,
            _FOOD_SAFETY_TITLE,
            ["Bill read a Third time and passed."],
        ),
    ]


def _seed_listing_entry(session: Session) -> None:
    capture = BillsSupplementCapture(
        original_url="https://sso.agc.gov.sg/Browse/Bills-Supp/Published/2024",
        archive_timestamp="20250109044700",
        capture_url="https://web.archive.org/web/20250109044700id_/https://sso.agc.gov.sg/Browse/Bills-Supp/Published/2024",
        content="<html></html>",
    )
    session.add(capture)
    session.flush()
    assert capture.id is not None
    session.add(
        BillsSupplementEntry(
            printed_title=_FOOD_SAFETY_TITLE,
            printed_number="Bill 49 of 2024",
            link="/Bills-Supp/49-2024/Published/20241112?DocDate=20241112",
            bill_number="49/2024",
            publication_date=date(2024, 11, 12),
            capture_id=capture.id,
        )
    )
    session.commit()


def _seed_egazette_rows(session: Session) -> None:
    session.add_all(
        [
            EgazetteSupplement(
                url=_BILLS_URL,
                year=2024,
                supplement_kind=EgazetteSupplementKind.BILLS,
                number=49,
                file_path="2024/bills/49.pdf",
                size_bytes=1,
                sha256="0" * 64,
                printed_title=_FOOD_SAFETY_TITLE,
                printed_bill_number="49/2024",
                bill_number="49/2024",
                first_reading_date=_FIRST_READING_DATE.date(),
                fetched_at=datetime(2026, 11, 8, tzinfo=timezone.utc),
            ),
            EgazetteSupplement(
                url=_ACTS_URL,
                year=2025,
                supplement_kind=EgazetteSupplementKind.ACTS,
                number=1,
                file_path="2025/acts/01.pdf",
                size_bytes=1,
                sha256="1" * 64,
                printed_title=_FOOD_SAFETY_TITLE,
                printed_bill_number="49/2024",
                bill_number="49/2024",
                first_reading_date=_FIRST_READING_DATE.date(),
                passing_date=_PASSING_DATE.date(),
                fetched_at=datetime(2026, 11, 8, tzinfo=timezone.utc),
            ),
        ]
    )
    session.commit()


def _write_harvest(directory: Path, act_text: str) -> None:
    (directory / "acts.json").write_text(
        json.dumps(
            [{"sso_code": "FSSA2025", "title": "Food Safety and Security Act 2025"}]
        ),
        encoding="utf8",
    )
    (directory / "FSSA2025.txt").write_text(act_text, encoding="utf8")


def test_the_plan_numbers_a_bill_from_the_listing_and_links_the_egazette_act(
    scratch_session: Session, tmp_path: Path
) -> None:
    report_ids = _seed_food_safety_reports(scratch_session)
    _seed_listing_entry(scratch_session)
    _seed_egazette_rows(scratch_session)
    _write_harvest(tmp_path, _FOOD_SAFETY_ACT_TEXT)

    plan = get_act_link_plan(scratch_session, tmp_path, [], [], [])

    (planned_bill,) = plan.bills
    assert planned_bill.report_ids == report_ids
    assert planned_bill.bill_number == "49/2024"
    assert planned_bill.bill_number_source == BillNumberSource.BILLS_SUPPLEMENT_LISTING
    assert [
        (egazette_link.url, egazette_link.bill_index)
        for egazette_link in plan.egazette_links
    ] == [(_ACTS_URL, 0)]
    (entry,) = plan.acts[0].entries
    assert entry.bill_index == 0
    assert entry.bill_link_source == BillLinkSource.FIRST_READING_DATE
    assert entry.bill_number_bill_index == 0


def test_the_plan_numbers_a_bill_from_the_egazette_when_the_listing_lacks_it(
    scratch_session: Session, tmp_path: Path
) -> None:
    _seed_food_safety_reports(scratch_session)
    _seed_egazette_rows(scratch_session)
    _write_harvest(tmp_path, _RENAMED_ACT_TEXT)

    plan = get_act_link_plan(scratch_session, tmp_path, [], [], [])

    (planned_bill,) = plan.bills
    assert planned_bill.bill_number == "49/2024"
    assert planned_bill.bill_number_source == BillNumberSource.EGAZETTE_BILLS_SUPPLEMENT
    (entry,) = plan.acts[0].entries
    assert entry.bill_index is None
    assert entry.bill_number_bill_index == 0


def test_the_write_sets_the_egazette_link_and_a_second_write_changes_nothing(
    scratch_session: Session, tmp_path: Path
) -> None:
    _seed_food_safety_reports(scratch_session)
    _seed_listing_entry(scratch_session)
    _seed_egazette_rows(scratch_session)
    _write_harvest(tmp_path, _FOOD_SAFETY_ACT_TEXT)
    plan = get_act_link_plan(scratch_session, tmp_path, [], [], [])

    write_act_link_plan(
        scratch_session, plan, get_act_link_write(scratch_session, plan)
    )
    scratch_session.commit()

    egazette_rows = {
        egazette_row.url: egazette_row
        for egazette_row in CRUDEgazetteSupplement(scratch_session).get_rows()
    }
    assert egazette_rows[_ACTS_URL].bill_id is not None
    assert (
        egazette_rows[_ACTS_URL].bill_link_source
        == BillLinkSource.BILL_NUMBER_PASSING_DATE
    )
    assert egazette_rows[_BILLS_URL].bill_id is None
    assert CRUDEgazetteSupplement(scratch_session).get_count_by_bill_id_not_null() == 1
    assert get_first_difference(get_act_link_write(scratch_session, plan)) is None
