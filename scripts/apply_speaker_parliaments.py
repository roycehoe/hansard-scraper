import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from database.init import engine
from database.speaker import Speaker
from exceptions import HansardWriteCheckError
from logs import logger
from populate.written_tables import vacuum_analyze_written_tables
from services.speaker import get_parliament_changes
from settings import settings
from utils.data_files import get_colonial_members, get_heads_of_state
from utils.write_target import validate_can_write


def apply_speaker_parliaments(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    colonial_members = get_colonial_members()
    heads_of_state = get_heads_of_state()
    with Session(engine) as session:
        parliament_changes = get_parliament_changes(CRUDSpeaker(session).get_all(), colonial_members, heads_of_state)
        for parliament_change in parliament_changes:
            logger.info(
                f"Speaker {parliament_change.id} {parliament_change.name}: "
                f"Parliament {parliament_change.parliament_number_before} -> {parliament_change.parliament_number_after}"
            )
        logger.info(f"Plan: {len(parliament_changes)} Parliament changes")
        if plan_path is not None:
            plan_path.write_text(json.dumps([asdict(parliament_change) for parliament_change in parliament_changes], indent=1, ensure_ascii=False))
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        updated_count = CRUDSpeaker(session).set_parliament_numbers_bulk(
            {parliament_change.id: parliament_change.parliament_number_after for parliament_change in parliament_changes}
        )
        if updated_count != len(parliament_changes):
            raise HansardWriteCheckError(f"Updated {updated_count} speaker rows, planned {len(parliament_changes)}")
        session.expire_all()
        if get_parliament_changes(CRUDSpeaker(session).get_all(), colonial_members, heads_of_state):
            raise HansardWriteCheckError("Parliament changes not applied after the update")
        session.commit()
        logger.info(f"Committed: {len(parliament_changes)} Parliament changes")
        vacuum_analyze_written_tables(session, [Speaker.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Move the Assembly-only speaker rows to the Parliament that data/colonial_la_members.json and data/heads_of_state.json give them")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    apply_speaker_parliaments(arguments.commit, arguments.plan)
