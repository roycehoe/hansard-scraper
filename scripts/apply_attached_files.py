import argparse

from sqlmodel import Session

from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from database.attached_file import AttachedFile
from database.attached_file_pointer import AttachedFilePointer
from database.init import engine
from logs import logger
from populate.attached_files import (
    AttachedFilePlan,
    get_attached_file_plan,
    get_planned_file_tie_count,
    get_stale_paragraph_tie_count,
    write_attached_file_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write

_DOWNLOAD_LINK_PATTERN = r"download\?value="
_NO_PARAGRAPH_LABEL = "no paragraph"


def _format_counts(name_to_count: dict[str, int]) -> str:
    return (
        ", ".join(f"{name} {count:,}" for name, count in sorted(name_to_count.items()))
        or "none"
    )


def _log_plan(
    plan: AttachedFilePlan, file_tie_count: int, stale_paragraph_tie_count: int
) -> None:
    pointers_with_address = (
        len(plan.attached_file_pointers) - plan.counts.pointers_without_address
    )
    logger.info(
        f"Files by kind: {_format_counts({kind.value: count for kind, count in plan.counts.kind_to_row_count.items()})}"
    )
    logger.info(
        f"Pointers by shape: {_format_counts({shape.value: count for shape, count in plan.counts.shape_to_row_count.items()})}"
    )
    logger.info(
        f"Paragraph ties by tier: {_format_counts({_NO_PARAGRAPH_LABEL if tie_rule is None else tie_rule.value: count for tie_rule, count in plan.counts.tie_rule_to_row_count.items()})}"
    )
    logger.info(f"Pointers that would take a file: {file_tie_count:,}")
    logger.info(
        f"Pointers with an address and no file: {pointers_with_address - file_tie_count:,}"
    )
    logger.info(f"Pointers with no address: {plan.counts.pointers_without_address:,}")
    logger.info(
        f"Links with a bad href in the reports read: {plan.counts.bad_file_links:,}"
    )
    logger.info(f"Stale paragraph ties: {stale_paragraph_tie_count:,}")
    logger.info(
        f"Plan: {len(plan.attached_files):,} files, {len(plan.attached_file_pointers):,} pointers for {len(plan.sprs_report_ids):,} reports"
    )


def apply_attached_files(report_ids: list[int], is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        is_every_sitting = not report_ids
        plan_report_ids = report_ids or CRUDReport(session).get_ids_by_content_regex(
            _DOWNLOAD_LINK_PATTERN
        )
        plan_sitting_ids = (
            CRUDSitting(session).get_ids_by_annexures_or_vernaculars_not_null()
            if is_every_sitting
            else []
        )
        plan = get_attached_file_plan(session, plan_report_ids, plan_sitting_ids)
        _log_plan(
            plan,
            get_planned_file_tie_count(session, plan, is_every_sitting),
            get_stale_paragraph_tie_count(session, plan_report_ids),
        )
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_attached_file_plan(session, plan, is_every_sitting)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session,
            [AttachedFile.__tablename__, AttachedFilePointer.__tablename__],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the files each sitting lists and the file pointers in each report's raw HTML, and tie them"
    )
    parser.add_argument(
        "--report-id",
        type=int,
        nargs="+",
        action="extend",
        default=[],
        help="only these reports, with no file rows written; without it every sitting and every report with a download link",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check the stored rows against the plan; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_attached_files(arguments.report_id, arguments.commit)
