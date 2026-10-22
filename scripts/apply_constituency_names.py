import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from services.attendance import (
    ConstituencyLookups,
    LocationChange,
    build_constituency_lookups,
    get_location_changes,
)
from settings import settings
from utils.data_files import get_constituency_names
from utils.write_target import validate_can_write


def _get_planned_changes(session: Session, constituency_lookups: ConstituencyLookups) -> list[LocationChange]:
    return get_location_changes(CRUDAttendance(session).get_location_rows_by_location_name_not_null(), constituency_lookups)


def apply_constituency_names(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    constituency_lookups = build_constituency_lookups(get_constituency_names())
    with Session(engine) as session:
        location_changes = _get_planned_changes(session, constituency_lookups)
        pair_to_count = Counter((change.location_name_before, change.location_name_after) for change in location_changes)
        for (location_name_before, location_name_after), count in sorted(pair_to_count.items()):
            logger.info(f"{count} rows: {location_name_before!r} -> {location_name_after!r}")
        logger.info(f"Plan: {len(location_changes)} location changes in {len(pair_to_count)} spellings")
        if plan_path is not None:
            plan_path.write_text(json.dumps([asdict(change) for change in location_changes], indent=1, ensure_ascii=False))
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        updated_count = CRUDAttendance(session).set_location_names_bulk({change.id: change.location_name_after for change in location_changes})
        if updated_count != len(location_changes):
            raise HansardWriteCheckError(f"Updated {updated_count} attendance rows, planned {len(location_changes)}")
        if _get_planned_changes(session, constituency_lookups):
            raise HansardWriteCheckError("Constituency names not applied after the update")
        session.commit()
        logger.info(f"Committed: {len(location_changes)} location changes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply data/constituency_names.json to the stored attendance location names")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    apply_constituency_names(arguments.commit, arguments.plan)
