from datetime import date, datetime
from pathlib import Path

import pytest
from sqlmodel import Session

from enums import ActHistoryEntryKind, BillLinkSource, ReportType
from exceptions import HansardHandKeptEntryError
from populate.act_links import get_act_link_plan
from schemas.act_link_plan import SkippedReport
from schemas.hand_kept_act_link import HandKeptActLink
from tests.bill_seed import seed_bill_report, write_harvest

_PASSING_LINE = "Question put, and agreed to.\n\nBill read a Third time and passed."


def test_plan_groups_bill_reports_and_reads_third_reading_lines(
    scratch_session: Session, tmp_path: Path
) -> None:
    first_reading_id = seed_bill_report(
        scratch_session,
        "first-reading",
        ReportType.BILL_INTRODUCTION,
        datetime(2024, 12, 2),
        "Estate Duty Bill",
        ["Bill read a First time."],
    )
    second_reading_id = seed_bill_report(
        scratch_session,
        "second-reading",
        ReportType.BILL,
        datetime(2025, 1, 14),
        "Estate Duty Bill",
        ["Mr Lim: I beg to move, That the Bill be now read a Second time."],
    )
    third_reading_id = seed_bill_report(
        scratch_session,
        "third-reading",
        ReportType.BILL,
        datetime(2025, 1, 15),
        "Estate Duty Bill",
        [_PASSING_LINE],
    )
    motion_id = seed_bill_report(
        scratch_session,
        "motion-to-read",
        ReportType.BILL,
        datetime(2025, 6, 2),
        "Water Bill",
        [
            "That the Bill be now read a Third time.",
            "Mr Tan: Sir, I thank members. The Bill read a Third time is good.",
        ],
    )
    adjournment_id = seed_bill_report(
        scratch_session,
        "adjournment",
        ReportType.BILL,
        datetime(2025, 1, 15),
        "ADJOURNMENT",
        [_PASSING_LINE],
    )
    other_type_id = seed_bill_report(
        scratch_session,
        "other-type",
        ReportType.MOTION,
        datetime(2025, 1, 15),
        "Sewage Bill",
        ["Mr Tan asked about the Sewage Bill."],
    )

    write_harvest(tmp_path)

    plan = get_act_link_plan(scratch_session, tmp_path, [], [], [])

    assert [
        (planned_bill.title_key, planned_bill.report_ids, planned_bill.is_passed)
        for planned_bill in plan.bills
    ] == [
        (
            "estatedutybill",
            [first_reading_id, second_reading_id, third_reading_id],
            True,
        ),
        ("waterbill", [motion_id], False),
    ]
    assert plan.skipped_reports == [
        SkippedReport(report_id=adjournment_id, title="ADJOURNMENT")
    ]
    assert other_type_id not in {
        report_id
        for planned_bill in plan.bills
        for report_id in planned_bill.report_ids
    }
    assert plan.unfetched_sso_codes == ["GONE1999"]
    assert plan.unparsed_entries == []
    assert [
        (planned_act.sso_code, len(planned_act.entries)) for planned_act in plan.acts
    ] == [("EDA2025", 2), ("WA2025", 0)]
    act_entry, revised_edition_entry = plan.acts[0].entries
    assert act_entry.kind == ActHistoryEntryKind.ACT
    assert act_entry.printed_bill_number == "9/2024"
    assert act_entry.third_reading_date == date(2025, 1, 15)
    assert act_entry.bill_index == 0
    assert act_entry.bill_link_source == BillLinkSource.FIRST_READING_DATE
    assert revised_edition_entry.kind == ActHistoryEntryKind.REVISED_EDITION
    assert revised_edition_entry.bill_index is None


def test_plan_splits_at_a_first_reading_line_but_not_at_a_new_clause_or_a_mention(
    scratch_session: Session, tmp_path: Path
) -> None:
    lapsed_first_reading_id = seed_bill_report(
        scratch_session,
        "lapsed-first-reading",
        ReportType.BILL_INTRODUCTION,
        datetime(1990, 11, 9),
        "ARCHITECTS BILL",
        ["Bill read the First time."],
    )
    lapsed_second_reading_id = seed_bill_report(
        scratch_session,
        "lapsed-second-reading",
        ReportType.BILL,
        datetime(1990, 12, 20),
        "ARCHITECTS BILL",
        ["Mr Lim: I beg to move, That the Bill be now read a Second time."],
    )
    reintroduction_id = seed_bill_report(
        scratch_session,
        "reintroduction",
        ReportType.BILL_INTRODUCTION,
        datetime(1991, 2, 26),
        "ARCHITECTS BILL",
        [
            '"to establish the Board of Architects", presented by the Minister for '
            "National Development (Mr Lim); read the first time; to be read a second "
            "time on the next available sitting of Parliament, and to be printed."
        ],
    )
    committee_id = seed_bill_report(
        scratch_session,
        "committee",
        ReportType.BILL,
        datetime(1991, 3, 22),
        "ARCHITECTS BILL",
        [
            "Brought up, and read the First time.",
            "_Brought up, and read the First time._",
            "Mr Tan: This Bill was read a First time on 26 February.",
            "Mr Tan: The Bill had been read the First time in this House.",
        ],
    )
    third_reading_id = seed_bill_report(
        scratch_session,
        "third-reading",
        ReportType.BILL,
        datetime(1991, 6, 28),
        "ARCHITECTS BILL",
        [_PASSING_LINE],
    )
    motion_to_read_id = seed_bill_report(
        scratch_session,
        "motion-to-read",
        ReportType.BILL,
        datetime(1991, 7, 3),
        "Stamp Bill",
        [
            'Sir, I present a Bill intituled "An Ordinance to amend the Stamp '
            'Ordinance (Chapter 170 of the Revised Edition)", and move that it be '
            "read the First time."
        ],
    )
    write_harvest(tmp_path)

    plan = get_act_link_plan(scratch_session, tmp_path, [], [], [])

    assert [
        (planned_bill.report_ids, planned_bill.is_passed) for planned_bill in plan.bills
    ] == [
        ([lapsed_first_reading_id, lapsed_second_reading_id], False),
        ([reintroduction_id, committee_id, third_reading_id], True),
        ([motion_to_read_id], False),
    ]


def _hand_kept_act_link(
    ordinal: int, printed_title: str, report_ids: list[int]
) -> HandKeptActLink:
    return HandKeptActLink(
        sso_code="EDA2025",
        ordinal=ordinal,
        printed_title=printed_title,
        report_ids=report_ids,
        reason="A reason.",
    )


def _seed_renamed_bill(session: Session) -> int:
    return seed_bill_report(
        session,
        "renamed",
        ReportType.BILL,
        datetime(1990, 3, 1),
        "Water Bill",
        ["Bill read a First time."],
    )


def test_plan_links_a_hand_kept_entry_to_the_bill_holding_exactly_its_reports(
    scratch_session: Session, tmp_path: Path
) -> None:
    report_id = _seed_renamed_bill(scratch_session)
    write_harvest(tmp_path)

    plan = get_act_link_plan(
        scratch_session,
        tmp_path,
        [],
        [],
        [_hand_kept_act_link(1, "Estate Duty Act 2025", [report_id])],
    )

    act_entry, revised_edition_entry = plan.acts[0].entries
    assert act_entry.bill_index == 0
    assert act_entry.bill_link_source == BillLinkSource.HAND_KEPT
    assert revised_edition_entry.bill_index is None


@pytest.mark.parametrize(
    ("hand_kept_act_link", "message"),
    [
        (_hand_kept_act_link(1, "Other Act 2025", [0]), "prints"),
        (_hand_kept_act_link(1, "Estate Duty Act 2025", [0, -1]), "no bill holds"),
        (
            _hand_kept_act_link(9, "Estate Duty Act 2025", [0]),
            "not an Act or Ordinance",
        ),
        (
            _hand_kept_act_link(2, "Estate Duty Act 2025", [0]),
            "not an Act or Ordinance",
        ),
    ],
)
def test_plan_raises_for_a_hand_kept_entry_that_no_longer_matches(
    hand_kept_act_link: HandKeptActLink,
    message: str,
    scratch_session: Session,
    tmp_path: Path,
) -> None:
    report_id = _seed_renamed_bill(scratch_session)
    write_harvest(tmp_path)
    hand_kept_act_link = hand_kept_act_link.model_copy(
        update={
            "report_ids": [
                report_id if report_id_in_file == 0 else report_id_in_file
                for report_id_in_file in hand_kept_act_link.report_ids
            ]
        }
    )

    with pytest.raises(HansardHandKeptEntryError, match=message):
        get_act_link_plan(scratch_session, tmp_path, [], [], [hand_kept_act_link])


def test_plan_groups_a_report_of_another_type_only_when_it_holds_a_reading_line(
    scratch_session: Session, tmp_path: Path
) -> None:
    bill_id = seed_bill_report(
        scratch_session,
        "bill-third-reading",
        ReportType.BILL,
        datetime(2003, 11, 20),
        "INSURANCE (AMENDMENT) BILL",
        [_PASSING_LINE],
    )
    motion_first_reading_id = seed_bill_report(
        scratch_session,
        "motion-first-reading",
        ReportType.MOTION,
        datetime(2003, 10, 16),
        "INSURANCE (AMENDMENT) BILL",
        ["Bill read a First time."],
    )
    motion_second_reading_id = seed_bill_report(
        scratch_session,
        "motion-second-reading",
        ReportType.MOTION,
        datetime(2004, 4, 19),
        "TRADE (AMENDMENT) BILL",
        ["Order for Second Reading read."],
    )
    oral_answer_id = seed_bill_report(
        scratch_session,
        "oral-answer",
        ReportType.ORAL_ANSWER,
        datetime(1986, 12, 9),
        "COPYRIGHT BILL",
        ["Mr Lim asked when the Copyright Bill will become law."],
    )
    select_committee_id = seed_bill_report(
        scratch_session,
        "select-committee",
        ReportType.MOTION,
        datetime(1994, 8, 26),
        "SELECT COMMITTEE ON THE MAINTENANCE OF PARENTS BILL",
        ["That Mr Tan be added to the Select Committee on the Bill."],
    )
    electricity_id = seed_bill_report(
        scratch_session,
        "electricity",
        ReportType.WRITTEN_ANSWER_NOT_AVAILABLE,
        datetime(2004, 10, 19),
        "UTILITIES BILL",
        ["Mr Lee asked how many bills the Bill read a Third time is about."],
    )
    write_harvest(tmp_path)

    plan = get_act_link_plan(scratch_session, tmp_path, [], [], [])

    assert [
        (planned_bill.title_key, planned_bill.report_ids, planned_bill.is_passed)
        for planned_bill in plan.bills
    ] == [
        (
            "insuranceamendmentbill",
            [motion_first_reading_id, bill_id],
            True,
        ),
        ("tradeamendmentbill", [motion_second_reading_id], False),
    ]
    assert {oral_answer_id, select_committee_id, electricity_id}.isdisjoint(
        report_id
        for planned_bill in plan.bills
        for report_id in planned_bill.report_ids
    )
