import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

from crud.division import CRUDDivision
from crud.division_party_count import CRUDDivisionPartyCount
from crud.division_vote import CRUDDivisionVote
from database.division_party_count import DivisionPartyCount
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from populate.division_party_counts import (
    get_division_party_count_plan,
    write_division_party_count_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from schemas.division_party_count_plan import DivisionPartyCountPlan
from settings import settings
from utils.sitting_dates import get_decade_label
from utils.write_target import validate_can_write


def _log_plan(session: Session, plan: DivisionPartyCountPlan) -> None:
    logger.info(
        f"Plan: {len(plan.party_counts):,} party count rows for {len(plan.division_ids):,} divisions"
    )
    division_id_to_decade = {
        division.id: get_decade_label(division.sitting_date)
        for division in CRUDDivision(session).get_by_ids(plan.division_ids)
    }
    decade_counts = Counter(
        division_id_to_decade[planned.division_id] for planned in plan.party_counts
    )
    logger.info(
        f"Rows by decade: {', '.join(f'{decade} {count:,}' for decade, count in sorted(decade_counts.items())) or 'none'}"
    )
    list_source_counts = Counter(planned.list_source for planned in plan.party_counts)
    logger.info(
        f"Rows by list source: {', '.join(f'{list_source} {count:,}' for list_source, count in sorted(list_source_counts.items())) or 'none'}"
    )
    vote_choice_counts = Counter(planned.vote_choice for planned in plan.party_counts)
    logger.info(
        f"Rows by vote choice: {', '.join(f'{vote_choice} {count:,}' for vote_choice, count in sorted(vote_choice_counts.items())) or 'none'}"
    )


def apply_division_party_counts(
    division_ids: list[int], plan_path: Path, is_commit: bool
) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_division_party_count_plan(
            session,
            division_ids
            or sorted(
                set(CRUDDivisionVote(session).get_distinct_division_ids())
                | set(CRUDDivisionPartyCount(session).get_distinct_division_ids())
            ),
        )
        if is_commit:
            reviewed_plan = DivisionPartyCountPlan.model_validate_json(
                plan_path.read_text()
            )
            if plan != reviewed_plan:
                raise HansardWriteCheckError("The plan differs from the reviewed plan")
        _log_plan(session, plan)
        if not is_commit:
            plan_path.write_text(plan.model_dump_json(indent=1))
            logger.info("Dry run: nothing written")
            return

        write_division_party_count_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [DivisionPartyCount.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the party breakdown of each division from its stored vote rows, checked against a reviewed plan"
    )
    parser.add_argument(
        "--division-id",
        type=int,
        nargs="+",
        action="extend",
        default=[],
        help="only these divisions; without it every division with a vote row or a stored breakdown",
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
    apply_division_party_counts(
        arguments.division_id, arguments.plan_file, arguments.commit
    )
