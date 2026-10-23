import argparse

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from database.init import engine
from database.speaker import Speaker
from logs import logger
from settings import settings
from utils.data_files import get_colonial_members, get_unscraped_members
from utils.write_target import validate_can_write


def store_colonial_speakers(session: Session, is_commit: bool) -> None:
    members = get_colonial_members() + get_unscraped_members()
    stored_keys = {(speaker.name, speaker.parliament_number) for speaker in CRUDSpeaker(session).get_all()}
    new_speakers = []
    for member in members:
        member_key = (member.name, member.parliament_number)
        if member_key in stored_keys:
            continue
        new_speakers.append(
            Speaker(
                name=member.name,
                party=member.party,
                is_legislative_assembly=member.is_legislative_assembly,
                parliament_number=member.parliament_number,
                comments=member.comments,
            )
        )
        stored_keys.add(member_key)

    logger.info(f"Plan: {len(new_speakers)} hand-typed speakers to insert ({len(members) - len(new_speakers)} already existed)")
    if not is_commit:
        logger.info("Dry run: nothing written")
        return

    CRUDSpeaker(session).add_many(new_speakers)
    session.commit()
    logger.info(f"Committed: {len(new_speakers)} hand-typed speakers inserted")


def load_colonial_la_speakers(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        store_colonial_speakers(session, is_commit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the members of data/colonial_la_members.json and data/unscraped_members.json that the speaker table lacks"
    )
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    arguments = parser.parse_args()
    load_colonial_la_speakers(arguments.commit)
