import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.head_of_state import HeadOfStateResult
from schemas.speaker import SpeakerResult
from services.speaker import get_parliament_changes
from settings import settings
from utils.write_target import validate_can_write

_COLONIAL_LA_MEMBERS_FILE = Path(__file__).parent.parent / "data" / "colonial_la_members.json"
_HEADS_OF_STATE_FILE = Path(__file__).parent.parent / "data" / "heads_of_state.json"


def apply_speaker_parliaments(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    colonial_members = [SpeakerResult.model_validate(record) for record in json.loads(_COLONIAL_LA_MEMBERS_FILE.read_text())]
    heads_of_state = [HeadOfStateResult.model_validate(record) for record in json.loads(_HEADS_OF_STATE_FILE.read_text())]
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Move the Assembly-only speaker rows to the Parliament that data/colonial_la_members.json and data/heads_of_state.json give them")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    apply_speaker_parliaments(arguments.commit, arguments.plan)
