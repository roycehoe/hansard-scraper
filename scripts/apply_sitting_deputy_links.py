import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from populate.speaker_links import get_sitting_deputy_speaker_ids
from services.attendance import build_speaker_lookups
from settings import settings
from utils.write_target import validate_can_write


def _validate_speaker_ids(session: Session, speech_id_to_speaker_id: dict[int, Optional[int]]) -> None:
    stored_speech_id_to_speaker_id = CRUDSpeech(session).get_speaker_ids_by_ids(list(speech_id_to_speaker_id))
    if len(stored_speech_id_to_speaker_id) != len(speech_id_to_speaker_id):
        raise HansardWriteCheckError(f"{len(stored_speech_id_to_speaker_id)} of {len(speech_id_to_speaker_id)} planned speech rows are stored")
    for speech_id, speaker_id in speech_id_to_speaker_id.items():
        if stored_speech_id_to_speaker_id[speech_id] != speaker_id:
            raise HansardWriteCheckError(f"Speech row {speech_id} holds speaker {stored_speech_id_to_speaker_id[speech_id]}, planned {speaker_id}")


def apply_sitting_deputy_links(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        speaker_id_to_name = {speaker.id: speaker.name for speaker in speakers}
        speaker_id_lookup = {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None}
        speech_id_to_speaker_id = get_sitting_deputy_speaker_ids(session, build_speaker_lookups(speakers), speaker_id_lookup)
        for speaker_id, count in Counter(speech_id_to_speaker_id.values()).most_common():
            logger.info(f"{count} rows: {speaker_id_to_name[speaker_id]}")
        logger.info(f"Plan: {len(speech_id_to_speaker_id)} bare Deputy Speaker rows to link")
        if plan_path is not None:
            plan_path.write_text(json.dumps(speech_id_to_speaker_id, indent=1))
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        session.expire_all()
        _validate_speaker_ids(session, dict.fromkeys(speech_id_to_speaker_id))
        CRUDSpeech(session).set_speaker_ids_bulk(speech_id_to_speaker_id)
        session.expire_all()
        _validate_speaker_ids(session, speech_id_to_speaker_id)
        session.commit()
        logger.info(f"Committed: {len(speech_id_to_speaker_id)} speech rows linked")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Link bare Deputy Speaker rows from the chair marks of the whole sitting")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    apply_sitting_deputy_links(arguments.commit, arguments.plan)
