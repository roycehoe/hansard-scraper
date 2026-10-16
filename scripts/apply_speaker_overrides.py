import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from database.init import engine
from database.speaker import Speaker
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.speaker_override import LegislativeAssemblyOverride, SpeakerOverrides
from settings import settings
from utils.write_target import validate_can_write

_SPEAKER_OVERRIDES_FILE = Path(__file__).parent.parent / "data" / "speaker_overrides.json"


@dataclass(frozen=True)
class FlagChange:
    id: int
    name: str
    parliament_number: int
    is_legislative_assembly_before: bool
    is_legislative_assembly_after: bool


def _get_flag_changes(speakers: list[Speaker], overrides: list[LegislativeAssemblyOverride]) -> list[FlagChange]:
    key_to_speaker = {(speaker.name, speaker.parliament_number): speaker for speaker in speakers}
    flag_changes = []
    for override in overrides:
        speaker = key_to_speaker.get((override.name, override.parliament_number))
        if speaker is None:
            raise HansardWriteCheckError(f"No speaker row for override {override.name!r}, Parliament {override.parliament_number}")
        if speaker.is_legislative_assembly == override.is_legislative_assembly:
            logger.info(f"Already applied: {override.name}, Parliament {override.parliament_number}")
            continue
        if speaker.is_legislative_assembly != override.source_is_legislative_assembly:
            raise HansardWriteCheckError(f"Speaker {speaker.id}: stored flag is neither the source value nor the override")
        flag_changes.append(FlagChange(speaker.id, speaker.name, speaker.parliament_number, speaker.is_legislative_assembly, override.is_legislative_assembly))
    return flag_changes


def _write_flags(session: Session, flag_changes: list[FlagChange], overrides: list[LegislativeAssemblyOverride]) -> None:
    updated_count = CRUDSpeaker(session).set_is_legislative_assembly_bulk(
        {flag_change.id: flag_change.is_legislative_assembly_after for flag_change in flag_changes}
    )
    if updated_count != len(flag_changes):
        raise HansardWriteCheckError(f"Updated {updated_count} speaker rows, planned {len(flag_changes)}")
    session.expire_all()
    if _get_flag_changes(CRUDSpeaker(session).get_all(), overrides):
        raise HansardWriteCheckError("Overrides not applied after the update")


def apply_speaker_overrides(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    overrides = SpeakerOverrides.model_validate(json.loads(_SPEAKER_OVERRIDES_FILE.read_text())).legislative_assembly_overrides
    with Session(engine) as session:
        flag_changes = _get_flag_changes(CRUDSpeaker(session).get_all(), overrides)
        for flag_change in flag_changes:
            logger.info(
                f"Speaker {flag_change.id} {flag_change.name}, Parliament {flag_change.parliament_number}: "
                f"is_legislative_assembly {flag_change.is_legislative_assembly_before} -> {flag_change.is_legislative_assembly_after}"
            )
        logger.info(f"Plan: {len(flag_changes)} speaker rows")
        if plan_path is not None:
            plan_path.write_text(json.dumps([asdict(flag_change) for flag_change in flag_changes], indent=1, ensure_ascii=False))
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        _write_flags(session, flag_changes, overrides)
        session.commit()
        logger.info(f"Committed: {len(flag_changes)} speaker rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply data/speaker_overrides.json to the stored speaker rows")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    apply_speaker_overrides(arguments.commit, arguments.plan)
