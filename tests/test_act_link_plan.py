from datetime import date, datetime
from pathlib import Path

from sqlmodel import Session

from enums import ActHistoryEntryKind, BillLinkSource, ReportType
from populate.act_links import get_act_link_plan
from schemas.act_link_plan import SkippedReport
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
        [_PASSING_LINE],
    )

    write_harvest(tmp_path)

    plan = get_act_link_plan(scratch_session, tmp_path, [], [])

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

    plan = get_act_link_plan(scratch_session, tmp_path, [], [])

    assert [
        (planned_bill.report_ids, planned_bill.is_passed) for planned_bill in plan.bills
    ] == [
        ([lapsed_first_reading_id, lapsed_second_reading_id], False),
        ([reintroduction_id, committee_id, third_reading_id], True),
        ([motion_to_read_id], False),
    ]
