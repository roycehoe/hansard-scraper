import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

from crud.egazette_supplement import CRUDEgazetteSupplement
from database.egazette_supplement import EgazetteSupplement
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from populate.egazette_supplements import (
    EgazetteSupplementWrite,
    get_egazette_supplement_plan,
    get_egazette_supplement_write,
    write_egazette_supplement_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from schemas.egazette_supplement_plan import EgazetteSupplementPlan
from settings import settings
from utils.write_target import validate_can_write


def _format_counts(counts: Counter[str]) -> str:
    return (
        ", ".join(f"{label} {count:,}" for label, count in sorted(counts.items()))
        or "none"
    )


def _log_plan(plan: EgazetteSupplementPlan) -> None:
    logger.info(
        f"Files by year and kind: {_format_counts(Counter(f'{supplement.year} {supplement.supplement_kind.value}' for supplement in plan.supplements))}"
    )
    logger.info(
        f"Parsed: {len(plan.supplements):,}; unparsed: {len(plan.unparsed):,}; 403 records: {plan.missing_count:,}"
    )
    for unparsed_supplement in plan.unparsed:
        logger.info(
            f"Unparsed: {unparsed_supplement.url}: {unparsed_supplement.message}"
        )


def _log_write(
    stored_count: int, egazette_supplement_write: EgazetteSupplementWrite
) -> None:
    logger.info(
        f"Rows already stored: {stored_count:,}; to insert: {len(egazette_supplement_write.supplements_to_insert):,}; to update: {len(egazette_supplement_write.supplement_updates):,}"
    )


def _validate_can_commit_egazette_supplements(
    session: Session, plan: EgazetteSupplementPlan
) -> None:
    stored_count = CRUDEgazetteSupplement(session).get_count()
    if stored_count != len(plan.supplements):
        raise HansardWriteCheckError(
            f"{stored_count} eGazette supplements are stored, the plan has {len(plan.supplements)}"
        )
    egazette_supplement_write = get_egazette_supplement_write(session, plan)
    if egazette_supplement_write.supplements_to_insert:
        raise HansardWriteCheckError(
            f"The stored rows lack {egazette_supplement_write.supplements_to_insert[0].url}"
        )
    if egazette_supplement_write.supplement_updates:
        raise HansardWriteCheckError(
            f"The stored row {egazette_supplement_write.supplement_updates[0].id} differs from the plan"
        )


def apply_egazette_supplements(
    harvest_directory: Path, plan_path: Path, is_commit: bool
) -> None:
    if not is_commit:
        plan = get_egazette_supplement_plan(harvest_directory)
        _log_plan(plan)
        with Session(engine) as session:
            _log_write(
                CRUDEgazetteSupplement(session).get_count(),
                get_egazette_supplement_write(session, plan),
            )
        plan_path.write_text(plan.model_dump_json(indent=1))
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = EgazetteSupplementPlan.model_validate_json(plan_path.read_text())
    plan = get_egazette_supplement_plan(harvest_directory)
    _log_plan(plan)
    if plan != reviewed_plan:
        raise HansardWriteCheckError("The plan differs from the reviewed plan")
    with Session(engine) as session:
        _log_write(
            CRUDEgazetteSupplement(session).get_count(),
            get_egazette_supplement_write(session, plan),
        )
        write_egazette_supplement_plan(session, plan)
        _validate_can_commit_egazette_supplements(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [EgazetteSupplement.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store one row per eGazette Bills Supplement and Acts Supplement PDF of a harvest directory, checked against a reviewed plan"
    )
    parser.add_argument(
        "--harvest-directory",
        type=Path,
        required=True,
        help="the fetch_egazette_supplements output: fetches.json and the PDFs",
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
        help="check the plan is unchanged, then apply it to the stored rows",
    )
    arguments = parser.parse_args()
    apply_egazette_supplements(
        arguments.harvest_directory, arguments.plan_file, arguments.commit
    )
