import argparse
from collections import Counter

from sqlmodel import Session

from database.init import engine
from database.ministry import Ministry
from database.ministry_see_also import MinistrySeeAlso
from database.office_title_ministry import OfficeTitleMinistry
from logs import logger
from populate.office_title_ministries import (
    MinistryPlan,
    get_ministry_plan,
    write_ministry_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.row_counts import format_row_counts
from utils.write_target import validate_can_write

_UNPLACED_TITLES_LOGGED = 50


def _log_plan(plan: MinistryPlan) -> None:
    source_to_row_count = Counter(
        placed_office_title.source for placed_office_title in plan.placed_office_titles
    )
    logger.info(
        f"Plan: {len(plan.ministry_names):,} ministries;"
        f" {len(plan.placed_office_titles):,} placements by source: {format_row_counts(source_to_row_count)};"
        f" {len(plan.role_only_titles):,} role-only titles;"
        f" {len(plan.unplaced_titles):,} unplaced titles;"
        f" {len(plan.ministry_see_also_entries):,} see-also entries"
    )
    for unplaced_title in plan.unplaced_titles[:_UNPLACED_TITLES_LOGGED]:
        logger.info(f"Unplaced title: {unplaced_title}")


def apply_ministries(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_ministry_plan(session)
        _log_plan(plan)
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_ministry_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session,
            [
                Ministry.__tablename__,
                OfficeTitleMinistry.__tablename__,
                MinistrySeeAlso.__tablename__,
            ],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the ministry names and place each printed office title under its ministries"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check the stored names and placements against the plan; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_ministries(arguments.commit)
