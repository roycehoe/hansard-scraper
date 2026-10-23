from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from gateway.speakers_by_parliament import get_parliament_member_list_response
from logs import logger
from services.speaker import (
    build_speaker,
    build_speaker_results,
    get_name_parliament_to_is_legislative_assembly,
    get_name_parliament_to_party,
)
from utils.data_files import get_speaker_overrides


def populate_speakers(session: Session, is_commit: bool) -> None:
    speaker_results = build_speaker_results(get_parliament_member_list_response())
    speaker_overrides = get_speaker_overrides()
    name_parliament_to_is_legislative_assembly = get_name_parliament_to_is_legislative_assembly(speaker_overrides)
    name_parliament_to_party = get_name_parliament_to_party(speaker_overrides)
    for i, speaker_result in enumerate(speaker_results, start=1):
        logger.info(f"{i}/{len(speaker_results)}: {speaker_result.name} (Parliament {speaker_result.parliament_number})")
    speakers = [
        build_speaker(speaker_result, name_parliament_to_is_legislative_assembly, name_parliament_to_party)
        for speaker_result in speaker_results
    ]
    if not is_commit:
        logger.info("Dry run: nothing written")
        return

    CRUDSpeaker(session).add_many(speakers)
    session.commit()
    logger.info(f"Committed: {len(speakers)} members inserted")
