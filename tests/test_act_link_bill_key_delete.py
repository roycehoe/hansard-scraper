import json
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, col, select

from crud.bill import CRUDBill
from crud.bill_key import CRUDBillKey
from database.bill_key import BillKey
from database.report import Report
from enums import ReportType
from populate.act_links import (
    get_act_link_plan,
    get_act_link_write,
    write_act_link_plan,
)
from tests.bill_seed import seed_bill_report

_FOOD_SAFETY_TITLE = "Food Safety and Security Bill"
_RENAMED_TITLE = "Food Supply Bill"
_FIRST_SPRS_REPORT_ID = "food-first"
_THIRD_SPRS_REPORT_ID = "food-third"
_FIRST_READING_DATE = datetime(2024, 11, 12)
_PASSING_DATE = datetime(2025, 1, 8)
_ACT_TEXT = """\
LEGISLATIVE HISTORY
 1. Act 3 of 2025 — Food Safety and Security Act 2025
     Bill                             :   49/2024
     First Reading                    :   12 November 2024
     Second and Third Readings        :   8 January 2025
     Commencement                     :   1 March 2025
Abbreviations
"""


def _write_harvest(directory: Path) -> None:
    (directory / "acts.json").write_text(
        json.dumps(
            [{"sso_code": "FSSA2025", "title": "Food Safety and Security Act 2025"}]
        ),
        encoding="utf8",
    )
    (directory / "FSSA2025.txt").write_text(_ACT_TEXT, encoding="utf8")


def _seed_food_safety_reports(session: Session) -> None:
    seed_bill_report(
        session,
        _FIRST_SPRS_REPORT_ID,
        ReportType.BILL_INTRODUCTION,
        _FIRST_READING_DATE,
        _FOOD_SAFETY_TITLE,
        ["Bill read a First time."],
    )
    seed_bill_report(
        session,
        _THIRD_SPRS_REPORT_ID,
        ReportType.BILL,
        _PASSING_DATE,
        _FOOD_SAFETY_TITLE,
        ["Bill read a Third time and passed."],
    )


def _write_plan(session: Session, harvest_directory: Path) -> list[int]:
    plan = get_act_link_plan(session, harvest_directory, [], [], [])
    act_link_write = get_act_link_write(session, plan)
    write_act_link_plan(session, plan, act_link_write)
    session.commit()
    return act_link_write.bill_ids_to_delete


def test_the_act_link_write_deletes_a_bill_that_has_a_key_row(
    scratch_session: Session, tmp_path: Path
) -> None:
    _seed_food_safety_reports(scratch_session)
    _write_harvest(tmp_path)
    _write_plan(scratch_session, tmp_path)
    old_bill_ids = [bill_row.id for bill_row in CRUDBill(scratch_session).get_rows()]
    assert len(old_bill_ids) == 1
    bill_id = old_bill_ids[0]
    scratch_session.add(
        BillKey(act_count=1, bill_key=_FIRST_SPRS_REPORT_ID, bill_id=bill_id)
    )
    scratch_session.commit()
    third_report = scratch_session.exec(
        select(Report).where(col(Report.report_id) == _THIRD_SPRS_REPORT_ID)
    ).one()
    third_report.title = _RENAMED_TITLE
    scratch_session.add(third_report)
    scratch_session.commit()

    bill_ids_to_delete = _write_plan(scratch_session, tmp_path)

    assert bill_ids_to_delete == [bill_id]
    scratch_session.expire_all()
    assert bill_id not in [
        bill_row.id for bill_row in CRUDBill(scratch_session).get_rows()
    ]
    assert CRUDBillKey(scratch_session).get_rows() == []


def test_a_second_act_link_write_leaves_the_key_rows_of_kept_bills(
    scratch_session: Session, tmp_path: Path
) -> None:
    _seed_food_safety_reports(scratch_session)
    _write_harvest(tmp_path)
    _write_plan(scratch_session, tmp_path)
    bill_id = CRUDBill(scratch_session).get_rows()[0].id
    scratch_session.add(
        BillKey(act_count=1, bill_key=_FIRST_SPRS_REPORT_ID, bill_id=bill_id)
    )
    scratch_session.commit()
    stored_key_id = CRUDBillKey(scratch_session).get_rows()[0].id

    bill_ids_to_delete = _write_plan(scratch_session, tmp_path)

    assert bill_ids_to_delete == []
    stored_key_rows = CRUDBillKey(scratch_session).get_rows()
    assert [
        (bill_key_row.id, bill_key_row.bill_id) for bill_key_row in stored_key_rows
    ] == [(stored_key_id, bill_id)]
