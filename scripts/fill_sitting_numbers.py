import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Optional

from sqlmodel import Session

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from settings import settings
from utils.markdown_header import (
    SESSION_NUMBER_FIELD,
    SITTING_NUMBER_FIELD,
    get_header_number,
)
from utils.sitting_dates import parse_sitting_date
from utils.write_target import validate_can_write


class NumberSource(StrEnum):
    SITTING_HEADER = "sitting header"
    REPORT_HEADER = "report header"
    SAME_DATE_SITTING = "sitting of the same date"


@dataclass(frozen=True)
class NumberFill:
    id: int
    sitting_date: str
    number: int
    source: NumberSource


@dataclass(frozen=True)
class NumberSkip:
    id: int
    sitting_date: str
    reason: str


@dataclass
class NumberPlan:
    session_fills: list[NumberFill] = field(default_factory=list)
    sitting_fills: list[NumberFill] = field(default_factory=list)
    report_fills: list[NumberFill] = field(default_factory=list)
    skips: list[NumberSkip] = field(default_factory=list)
    disagreements: list[NumberSkip] = field(default_factory=list)


def _add_sitting_numbers(plan: NumberPlan, session: Session) -> dict[date, int]:
    sitting_day_to_sitting_number = {}
    for sitting_row in CRUDSitting(session).get_number_rows():
        markdown = sitting_row.markdown_content or ""
        header_session_number = get_header_number(markdown, SESSION_NUMBER_FIELD)
        header_sitting_number = get_header_number(markdown, SITTING_NUMBER_FIELD)
        if sitting_row.session_no is None and header_session_number is not None:
            plan.session_fills.append(NumberFill(sitting_row.id, sitting_row.sitting_date, header_session_number, NumberSource.SITTING_HEADER))
        if sitting_row.session_no is None and header_session_number is None:
            plan.skips.append(NumberSkip(sitting_row.id, sitting_row.sitting_date, "sitting session_no: no Session No line in the sitting header"))
        if sitting_row.sitting_no is None and header_sitting_number is not None:
            plan.sitting_fills.append(NumberFill(sitting_row.id, sitting_row.sitting_date, header_sitting_number, NumberSource.SITTING_HEADER))
        if sitting_row.sitting_no is None and header_sitting_number is None:
            plan.skips.append(NumberSkip(sitting_row.id, sitting_row.sitting_date, "sitting sitting_no: no Sitting No line in the sitting header"))
        if sitting_row.sitting_no is not None and header_sitting_number is not None and sitting_row.sitting_no != header_sitting_number:
            plan.disagreements.append(NumberSkip(sitting_row.id, sitting_row.sitting_date, f"sitting_no {sitting_row.sitting_no}, header {header_sitting_number}"))
        sitting_number = header_sitting_number if sitting_row.sitting_no is None else sitting_row.sitting_no
        if sitting_number is not None:
            sitting_day_to_sitting_number[parse_sitting_date(sitting_row.sitting_date).date()] = sitting_number
    return sitting_day_to_sitting_number


def _add_report_numbers(plan: NumberPlan, session: Session, sitting_day_to_sitting_number: dict[date, int]) -> None:
    for report_row in CRUDReport(session).get_markdown_rows_by_sitting_number_null():
        sitting_date = f"{report_row.sitting_date:%d-%m-%Y}"
        header_sitting_number = get_header_number(report_row.markdown_content or "", SITTING_NUMBER_FIELD)
        if header_sitting_number is not None:
            plan.report_fills.append(NumberFill(report_row.id, sitting_date, header_sitting_number, NumberSource.REPORT_HEADER))
            continue
        sitting_number: Optional[int] = sitting_day_to_sitting_number.get(report_row.sitting_date.date())
        if sitting_number is not None:
            plan.report_fills.append(NumberFill(report_row.id, sitting_date, sitting_number, NumberSource.SAME_DATE_SITTING))
            continue
        plan.skips.append(NumberSkip(report_row.id, sitting_date, "report sitting_number: no header and no sitting number for the date"))


def _write_numbers(plan: NumberPlan, session: Session) -> None:
    session_count = CRUDSitting(session).set_session_numbers_bulk({fill.id: fill.number for fill in plan.session_fills})
    sitting_count = CRUDSitting(session).set_sitting_numbers_bulk({fill.id: fill.number for fill in plan.sitting_fills})
    report_count = CRUDReport(session).set_sitting_numbers_bulk({fill.id: fill.number for fill in plan.report_fills})
    if session_count != len(plan.session_fills):
        raise HansardWriteCheckError(f"Updated {session_count} sitting session numbers, planned {len(plan.session_fills)}")
    if sitting_count != len(plan.sitting_fills):
        raise HansardWriteCheckError(f"Updated {sitting_count} sitting numbers, planned {len(plan.sitting_fills)}")
    if report_count != len(plan.report_fills):
        raise HansardWriteCheckError(f"Updated {report_count} report sitting numbers, planned {len(plan.report_fills)}")
    after_plan = NumberPlan()
    _add_report_numbers(after_plan, session, _add_sitting_numbers(after_plan, session))
    if after_plan.session_fills or after_plan.sitting_fills or after_plan.report_fills:
        raise HansardWriteCheckError("Rows the plan fills are still empty after the update")
    if len(after_plan.skips) != len(plan.skips):
        raise HansardWriteCheckError(f"{len(after_plan.skips)} empty values after the update, planned {len(plan.skips)}")


def fill_sitting_numbers(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = NumberPlan()
        _add_report_numbers(plan, session, _add_sitting_numbers(plan, session))
        logger.info(
            f"Plan: {len(plan.session_fills)} sitting session numbers, {len(plan.sitting_fills)} sitting numbers, "
            f"{len(plan.report_fills)} report sitting numbers; {len(plan.skips)} left empty; "
            f"{len(plan.disagreements)} stored sitting numbers that differ from the header, left as stored"
        )
        for skip in plan.skips + plan.disagreements:
            logger.info(f"Left as stored: {skip.id} ({skip.sitting_date}) {skip.reason}")
        if plan_path is not None:
            plan_path.write_text(json.dumps(asdict(plan), indent=2))
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        _write_numbers(plan, session)
        session.commit()
        logger.info("Committed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fill empty report and sitting numbers from the header tables the scraper stores")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    fill_sitting_numbers(arguments.commit, arguments.plan)
