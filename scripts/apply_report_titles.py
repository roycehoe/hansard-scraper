import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from sqlmodel import Session

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.report import CRUDReport, ReportTitleRow
from database.init import engine
from database.report import Report
from exceptions import HansardWriteCheckError
from logs import logger
from populate.written_tables import vacuum_analyze_written_tables
from services.report import build_report_header
from settings import settings
from utils.text import fix_mojibake
from utils.write_target import validate_can_write

_UPDATE_BATCH = 200


@dataclass(frozen=True)
class TitleChange:
    id: int
    title_before: str
    subtitle_before: Optional[str]
    title_after: str
    subtitle_after: Optional[str]


def _get_title_changes(title_rows: list[ReportTitleRow]) -> list[TitleChange]:
    title_changes = []
    for title_row in title_rows:
        report_header = build_report_header(fix_mojibake(title_row.original_title))
        # NOTE: only a stored title the rule builds differently is changed; a row whose subtitle alone is stale stays as stored.
        if report_header.title == title_row.title:
            continue
        title_changes.append(TitleChange(title_row.id, title_row.title, title_row.subtitle, report_header.title, report_header.subtitle))
    return title_changes


def _write_titles(session: Session, title_changes: list[TitleChange]) -> None:
    id_to_title_change = {title_change.id: title_change for title_change in title_changes}
    report_ids = list(id_to_title_change)
    for start in range(0, len(report_ids), _UPDATE_BATCH):
        for report in CRUDReport(session).get_by_ids(report_ids[start:start + _UPDATE_BATCH]):
            title_change = id_to_title_change[report.id]
            if report.title != title_change.title_before or report.subtitle != title_change.subtitle_before:
                raise HansardWriteCheckError(f"Report {report.id}: title changed since the plan was made")
            report.title = title_change.title_after
            report.subtitle = title_change.subtitle_after
            CRUDReport(session).update(report)
        session.expunge_all()
    if _get_title_changes(CRUDReport(session).get_title_rows()):
        raise HansardWriteCheckError("Titles the rule rewrites remain after the update")


def apply_report_titles(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        title_changes = _get_title_changes(CRUDReport(session).get_title_rows())
        for title_change in title_changes:
            logger.info(f"Report {title_change.id}: {title_change.title_before!r} {title_change.subtitle_before!r} -> {title_change.title_after!r} {title_change.subtitle_after!r}")
        logger.info(f"Plan: {len(title_changes)} report titles")
        if plan_path is not None:
            plan_path.write_text(json.dumps([asdict(title_change) for title_change in title_changes], indent=1, ensure_ascii=False))
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        _write_titles(session, title_changes)
        session.commit()
        logger.info(f"Committed: {len(title_changes)} report titles")
        vacuum_analyze_written_tables(session, [Report.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rewrite stored report titles with the current title rule")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    apply_report_titles(arguments.commit, arguments.plan)
