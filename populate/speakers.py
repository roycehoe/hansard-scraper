from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from gateway.speakers_by_parliament import get_all_speakers
from logs import logger
from services.speaker import build_speaker
from utils.data_files import get_speaker_overrides


def load_name_parliament_to_is_legislative_assembly() -> dict[tuple[str, int], bool]:
    speaker_overrides = get_speaker_overrides()
    return {
        (override.name, override.parliament_number): override.is_legislative_assembly
        for override in speaker_overrides.legislative_assembly_overrides
    }


def load_name_parliament_to_party() -> dict[tuple[str, int], str]:
    speaker_overrides = get_speaker_overrides()
    return {(override.name, override.parliament_number): override.party for override in speaker_overrides.party_overrides}


def populate_speakers(session: Session) -> None:
    speakers = get_all_speakers()
    name_parliament_to_is_legislative_assembly = load_name_parliament_to_is_legislative_assembly()
    name_parliament_to_party = load_name_parliament_to_party()
    for i, speaker_result in enumerate(speakers, start=1):
        logger.info(f"{i}/{len(speakers)}: {speaker_result.name} (Parliament {speaker_result.parliament_number})")
        CRUDSpeaker(session).create(
            build_speaker(speaker_result, name_parliament_to_is_legislative_assembly, name_parliament_to_party)
        )
