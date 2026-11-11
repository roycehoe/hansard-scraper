import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

from crud.report import CRUDReport
from database.division import Division
from database.division_vote import DivisionVote
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from populate.divisions import (
    get_decade_and_source_counts,
    get_division_match,
    get_division_plan,
    get_paired_divisions_at_risk,
    write_division_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from schemas.division_plan import DivisionPlan
from settings import settings
from utils.sitting_dates import get_decade_label
from utils.write_target import validate_can_write


def _log_plan(session: Session, plan: DivisionPlan) -> None:
    logger.info(
        f"Plan: {len(plan.divisions):,} divisions in {len(plan.report_ids):,} reports, {len(plan.unread_rows):,} unread rows"
    )
    decade_and_source_counts = get_decade_and_source_counts(plan.divisions)
    logger.info(
        f"Divisions by decade and source: {', '.join(f'{decade} {source} {count:,}' for (decade, source), count in sorted(decade_and_source_counts.items()))}"
    )
    decade_and_list_status_counts = Counter(
        (get_decade_label(division.sitting_date), division.list_status)
        for division in plan.divisions
    )
    logger.info(
        f"Divisions by decade and list status: {', '.join(f'{decade} {list_status} {count:,}' for (decade, list_status), count in sorted(decade_and_list_status_counts.items()))}"
    )
    vote_counts = Counter(
        (vote.vote_choice, "linked" if vote.speaker_id is not None else "unlinked")
        for division in plan.divisions
        for vote in division.votes
    )
    logger.info(
        f"Hansard vote rows by choice and link: {', '.join(f'{vote_choice} {link} {count:,}' for (vote_choice, link), count in sorted(vote_counts.items())) or 'none'}"
    )
    reason_to_count = Counter(unread_row.reason for unread_row in plan.unread_rows)
    logger.info(
        f"Unread rows by reason: {', '.join(f'{reason} {count:,}' for reason, count in sorted(reason_to_count.items())) or 'none'}"
    )
    match = get_division_match(session, plan)
    updated_count = len(match.division_updates)
    added_count = len(match.divisions_to_add)
    kept_count = len(plan.divisions) - updated_count - added_count
    logger.info(
        f"Against stored: {kept_count:,} kept, {updated_count:,} updated, {added_count:,} added, {len(match.division_ids_to_delete):,} deleted"
    )


def _log_paired_at_risk(session: Session, plan: DivisionPlan) -> None:
    at_risk_divisions = get_paired_divisions_at_risk(session, plan)
    for at_risk in at_risk_divisions:
        logger.info(
            f"Paired division {at_risk.division_id} of report {at_risk.sprs_report_id} ({at_risk.printed_counts}): {'line gone' if at_risk.is_line_gone else 'counts would change'}"
        )
    logger.info(
        f"Plan: {len(at_risk_divisions):,} paired divisions at risk, {sum(at_risk.is_line_gone for at_risk in at_risk_divisions):,} with the line gone"
    )


def apply_divisions(
    report_ids: list[int], plan_path: Path, is_commit: bool, is_detach_paired: bool
) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_division_plan(session, report_ids or CRUDReport(session).get_ids())
        if is_commit:
            reviewed_plan = DivisionPlan.model_validate_json(plan_path.read_text())
            if plan != reviewed_plan:
                raise HansardWriteCheckError("The plan differs from the reviewed plan")
        _log_plan(session, plan)
        _log_paired_at_risk(session, plan)
        if not is_commit:
            plan_path.write_text(plan.model_dump_json(indent=1))
            logger.info("Dry run: nothing written")
            return

        write_division_plan(session, plan, is_detaching_paired=is_detach_paired)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session, [Division.__tablename__, DivisionVote.__tablename__]
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the divisions of each report, read from its speech rows, checked against a reviewed plan"
    )
    parser.add_argument(
        "--report-id",
        type=int,
        nargs="+",
        action="extend",
        default=[],
        help="only these reports; without it every report",
    )
    parser.add_argument(
        "--plan-file",
        type=Path,
        required=True,
        help="the plan file: written by a dry run, read by --commit",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="check the plan is unchanged, then write it, check the stored counts by decade and source against the plan, and commit",
    )
    parser.add_argument(
        "--detach-paired",
        action="store_true",
        help="rewrite a paired division whose line has gone to a minutes-only division; without it the write refuses",
    )
    arguments = parser.parse_args()
    apply_divisions(
        arguments.report_id,
        arguments.plan_file,
        arguments.commit,
        arguments.detach_paired,
    )
