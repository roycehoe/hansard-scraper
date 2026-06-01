from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from gateway.speakers_by_parliament import get_all_speakers
from logs import logger
from services.speaker import build_speaker


def populate_speakers(session: Session) -> None:
    crud = CRUDSpeaker(session)
    speakers = get_all_speakers()
    for i, speaker_result in enumerate(speakers, start=1):
        logger.info(f"{i}/{len(speakers)}: {speaker_result.name} (Parliament {speaker_result.parliament_number})")
        crud.create(build_speaker(speaker_result))
