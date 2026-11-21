import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.report_picture import CRUDReportPicture
from database.init import engine
from database.report_picture import ReportPicture
from exceptions import HansardWriteCheckError
from logs import logger
from populate.report_pictures import (
    ReportPictureWrite,
    get_planned_report_pictures,
    get_report_picture_write,
    write_report_picture_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from schemas.report_picture_plan import ReportPicturePlan
from settings import settings
from utils.write_target import validate_can_write


def _format_counts(counts: Counter[str]) -> str:
    return (
        ", ".join(f"{label} {count:,}" for label, count in sorted(counts.items()))
        or "none"
    )


def _log_plan(plan: ReportPicturePlan) -> None:
    logger.info(
        f"Pictures by kind: {_format_counts(Counter(planned_picture.kind.value for planned_picture in plan.pictures))}"
    )
    logger.info(
        f"Plan: {len(plan.pictures):,} pictures in {len({planned_picture.report_id for planned_picture in plan.pictures}):,} reports"
    )


def _log_write(stored_count: int, report_picture_write: ReportPictureWrite) -> None:
    logger.info(
        f"Rows already stored: {stored_count:,}; to insert: {len(report_picture_write.pictures_to_insert):,}; to update: {len(report_picture_write.picture_updates):,}; to delete: {len(report_picture_write.row_ids_to_delete):,}"
    )


def _validate_can_commit_report_pictures(
    session: Session, report_pictures: list[ReportPicture]
) -> None:
    stored_count = CRUDReportPicture(session).get_count()
    if stored_count != len(report_pictures):
        raise HansardWriteCheckError(
            f"{stored_count} report pictures are stored, the plan has {len(report_pictures)}"
        )
    report_picture_write = get_report_picture_write(session, report_pictures)
    if report_picture_write.pictures_to_insert:
        raise HansardWriteCheckError(
            f"The stored rows lack picture {report_picture_write.pictures_to_insert[0].picture_index} of report {report_picture_write.pictures_to_insert[0].report_id}"
        )
    if report_picture_write.picture_updates:
        raise HansardWriteCheckError(
            f"The stored row {report_picture_write.picture_updates[0].id} differs from the plan"
        )
    if report_picture_write.row_ids_to_delete:
        raise HansardWriteCheckError(
            f"The stored row {report_picture_write.row_ids_to_delete[0]} is not in the plan"
        )


def apply_report_pictures(plan_path: Path, is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    plan = ReportPicturePlan.model_validate_json(plan_path.read_text(encoding="utf8"))
    _log_plan(plan)
    with Session(engine) as session:
        report_pictures = get_planned_report_pictures(session, plan)
        _log_write(
            CRUDReportPicture(session).get_count(),
            get_report_picture_write(session, report_pictures),
        )
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_report_picture_plan(session, report_pictures)
        _validate_can_commit_report_pictures(session, report_pictures)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [ReportPicture.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store each inline picture of report.content with its kind, anchor and typed copy, checked against a plan file"
    )
    parser.add_argument(
        "--plan-file",
        type=Path,
        required=True,
        help="the pictures to store: report id, picture index, offset, SHA-256, kind, follows_ordinal and typed copy",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check the stored rows against the plan; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_report_pictures(arguments.plan_file, arguments.commit)
