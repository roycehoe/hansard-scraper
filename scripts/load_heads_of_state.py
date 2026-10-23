import argparse

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from database.init import engine
from database.speaker import Speaker
from exceptions import HansardWriteCheckError
from logs import logger
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.data_files import get_heads_of_state
from utils.write_target import validate_can_write

_NON_PARTISAN_PARTY = "Non-partisan"


def store_heads_of_state(session: Session, is_commit: bool) -> None:
    name_and_parliament_number_to_speaker = {(speaker.name, speaker.parliament_number): speaker for speaker in CRUDSpeaker(session).get_all()}
    new_speakers = []
    speaker_id_to_is_member = {}
    for head_of_state in get_heads_of_state():
        head_of_state_key = (head_of_state.name, head_of_state.parliament_number)
        speaker = name_and_parliament_number_to_speaker.get(head_of_state_key)
        if speaker is None:
            new_speaker = Speaker(
                name=head_of_state.name,
                parliament_number=head_of_state.parliament_number,
                comments=head_of_state.comments,
                party=_NON_PARTISAN_PARTY,
                is_legislative_assembly=False,
                is_member=False,
            )
            new_speakers.append(new_speaker)
            name_and_parliament_number_to_speaker[head_of_state_key] = new_speaker
            continue
        if speaker.is_member:
            speaker_id_to_is_member[speaker.id] = False

    logger.info(f"Plan: insert {len(new_speakers)} head-of-state speakers, mark {len(speaker_id_to_is_member)} existing rows as non-members")
    if not is_commit:
        logger.info("Dry run: nothing written")
        return

    CRUDSpeaker(session).add_many(new_speakers)
    updated_count = CRUDSpeaker(session).set_is_member_bulk(speaker_id_to_is_member)
    if updated_count != len(speaker_id_to_is_member):
        raise HansardWriteCheckError(f"Updated {updated_count} speaker rows, planned {len(speaker_id_to_is_member)}")
    session.commit()
    logger.info(f"Committed: {len(new_speakers)} head-of-state speakers inserted, {updated_count} existing rows marked as non-members")


def load_heads_of_state(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        store_heads_of_state(session, is_commit)
        if is_commit:
            vacuum_analyze_written_tables(session, [Speaker.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Store the heads of state of data/heads_of_state.json as non-member speakers")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    arguments = parser.parse_args()
    load_heads_of_state(arguments.commit)
