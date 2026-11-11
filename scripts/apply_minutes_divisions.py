import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

from crud.minutes import CRUDMinutes
from database.division import Division
from database.division_vote import DivisionVote
from database.init import engine
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from exceptions import HansardWriteCheckError
from logs import logger
from populate.minutes_divisions import (
    MINUTES_DIVISION_FIRST_DATE,
    get_minutes_division_plan,
    write_minutes_division_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from schemas.minutes_division_plan import MinutesDivisionPlan
from settings import settings
from utils.sitting_dates import get_decade_label
from utils.write_target import validate_can_write


def _log_plan(plan: MinutesDivisionPlan) -> None:
    logger.info(
        f"Plan: {len(plan.minutes_divisions):,} divisions in {len(plan.minutes_ids):,} minutes files"
    )
    decade_counts = Counter(
        get_decade_label(planned.sitting_date) for planned in plan.minutes_divisions
    )
    logger.info(
        f"Divisions by decade: {', '.join(f'{decade} {count:,}' for decade, count in sorted(decade_counts.items())) or 'none'}"
    )
    list_status_counts = Counter(
        planned.list_status for planned in plan.minutes_divisions
    )
    logger.info(
        f"Divisions by list status: {', '.join(f'{list_status} {count:,}' for list_status, count in sorted(list_status_counts.items())) or 'none'}"
    )
    pairing_counts = Counter(planned.pairing for planned in plan.minutes_divisions)
    logger.info(
        f"Divisions by pairing: {', '.join(f'{pairing} {count:,}' for pairing, count in sorted(pairing_counts.items())) or 'none'}"
    )
    linked_count = sum(
        vote.speaker_id is not None
        for planned in plan.minutes_divisions
        for vote in planned.votes
    )
    unlinked_count = sum(len(planned.votes) for planned in plan.minutes_divisions)
    logger.info(
        f"Vote rows: {linked_count:,} linked, {unlinked_count - linked_count:,} unlinked"
    )
    logger.info(f"Files to review: {len(plan.minutes_to_review):,}")
    for minutes_review in plan.minutes_to_review:
        logger.info(
            f"Review minutes {minutes_review.minutes_id}: {minutes_review.status_note}"
        )


def apply_minutes_divisions(
    minutes_ids: list[int], plan_path: Path, is_commit: bool
) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_minutes_division_plan(
            session,
            minutes_ids
            or [
                minutes.id
                for minutes in CRUDMinutes(
                    session
                ).get_by_sitting_date_from_and_extracted_text_not_null(
                    MINUTES_DIVISION_FIRST_DATE
                )
                if minutes.id is not None
            ],
        )
        if is_commit:
            reviewed_plan = MinutesDivisionPlan.model_validate_json(
                plan_path.read_text()
            )
            if plan != reviewed_plan:
                raise HansardWriteCheckError("The plan differs from the reviewed plan")
        _log_plan(plan)
        if not is_commit:
            plan_path.write_text(plan.model_dump_json(indent=1))
            logger.info("Dry run: nothing written")
            return

        write_minutes_division_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session,
            [
                MinutesDivision.__tablename__,
                DivisionVote.__tablename__,
                Division.__tablename__,
                Minutes.__tablename__,
            ],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the divisions and vote rows of each minutes file, paired with the Hansard divisions, checked against a reviewed plan"
    )
    parser.add_argument(
        "--minutes-id",
        type=int,
        nargs="+",
        action="extend",
        default=[],
        help="only these minutes; without it every file with text from 1 October 2008",
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
        help="check the plan is unchanged, then write it, check the stored counts against the plan, and commit",
    )
    arguments = parser.parse_args()
    apply_minutes_divisions(arguments.minutes_id, arguments.plan_file, arguments.commit)
