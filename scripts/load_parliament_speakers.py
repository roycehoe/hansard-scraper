import argparse

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from database.init import engine
from gateway.speakers_by_parliament import get_speakers_by_parliament_number
from logs import logger
from populate.speakers import (
    load_name_parliament_to_is_legislative_assembly,
    load_name_parliament_to_party,
)
from services.speaker import build_speaker
from settings import settings
from utils.write_target import validate_can_write


def load_parliament_speakers(session: Session, parliament_number: int, is_commit: bool) -> None:
    stored_keys = {(speaker.name, speaker.parliament_number) for speaker in CRUDSpeaker(session).get_all()}
    speaker_results = get_speakers_by_parliament_number(parliament_number)
    name_parliament_to_is_legislative_assembly = load_name_parliament_to_is_legislative_assembly()
    name_parliament_to_party = load_name_parliament_to_party()
    new_speakers = [
        build_speaker(speaker_result, name_parliament_to_is_legislative_assembly, name_parliament_to_party)
        for speaker_result in speaker_results
        if (speaker_result.name, speaker_result.parliament_number) not in stored_keys
    ]
    skipped = len(speaker_results) - len(new_speakers)
    for speaker in new_speakers:
        logger.info(f"New member: {speaker.name} ({speaker.party}), Parliament {speaker.parliament_number}")
    logger.info(f"{len(new_speakers)} new members for Parliament {parliament_number}, {skipped} already stored")
    if not is_commit:
        logger.info("Dry run: nothing written")
        return

    for speaker in new_speakers:
        CRUDSpeaker(session).create(speaker)
    logger.info(f"Committed: {len(new_speakers)} members inserted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Store the members of one Parliament that the speaker table lacks, from parliament.gov.sg")
    parser.add_argument("--parliament", type=int, required=True, help="the Parliament number whose member list to load")
    parser.add_argument("--commit", action="store_true", dest="is_commit", help="write; without it the script only reports the plan")
    arguments = parser.parse_args()
    if arguments.is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        load_parliament_speakers(session, arguments.parliament, arguments.is_commit)
