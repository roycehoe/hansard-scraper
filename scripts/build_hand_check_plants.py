import argparse
import hashlib
import random
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.person import CRUDPerson
from crud.speaker import CRUDSpeaker
from crud.speech import (
    CRUDSpeech,
    SpeechParseRow,
    SpeechSnapshotRow,
    SpeechTranscriptRow,
)
from database.init import build_read_only_engine
from database.speaker import Speaker
from enums import HandCheckPlantKind, SpeechKind
from exceptions import HansardHandCheckError
from logs import logger
from schemas.hand_check_plant_key import HandCheckPlant, HandCheckPlantKey
from schemas.hand_check_snapshot import (
    HandCheckSnapshot,
    HandCheckSnapshotRow,
    HandCheckSnapshotRows,
)
from services.speech import APPENDIX_LINK_CAPTION_RE
from settings import settings

_FIRST_ROUND_NUMBER = 1
_PLANT_ROUND_TO_SEED = {1: 20_261_103, 2: 20_261_104}
_PLANT_ISOLATION_LEVEL = "REPEATABLE READ"
_PLANT_KIND_TO_COUNT = {
    HandCheckPlantKind.WRONG_MEMBER: 15,
    HandCheckPlantKind.CREDITED_NON_SPEECH_LINE: 15,
}
_ROLE_LABEL_RE = re.compile(
    r"^(?:(?:The|Mr|Mdm|Madam)\s+Chairman"
    r"|(?:Mr|Mdm|Madam)\s+Speaker"
    r"|(?:Mr|Mdm|Madam|The)\s+Deputy\s*Speaker"
    r"|(?:The|His Excellency the)\s+[^()]+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CreditLookups:
    speaker_id_to_speaker: dict[int, Speaker]
    person_id_to_canonical_name: dict[int, str]


@dataclass(frozen=True)
class PlantedRow:
    snapshot_row: HandCheckSnapshotRow
    plant: HandCheckPlant


def get_nearest_credited_row_above(
    parse_rows: list[SpeechParseRow], ordinal: int
) -> Optional[SpeechParseRow]:
    for report_row in reversed(parse_rows):
        if report_row.ordinal < ordinal and report_row.speaker_id is not None:
            return report_row
    return None


def get_next_row(
    report_rows: list[SpeechParseRow], speech_id: int
) -> Optional[SpeechParseRow]:
    return next(
        (
            next_row
            for report_row, next_row in pairwise(report_rows)
            if report_row.id == speech_id
        ),
        None,
    )


def is_role_label(label: Optional[str]) -> bool:
    return label is not None and _ROLE_LABEL_RE.match(label) is not None


def get_non_speech_speech_ids(
    procedural_rows: list[SpeechTranscriptRow],
    editorial_note_rows: list[SpeechTranscriptRow],
    excluded_speech_ids: set[int],
) -> list[int]:
    # NOTE: the regex runs here, not in SQL, as Postgres regex syntax could change the match the parser makes.
    caption_rows = [
        editorial_note_row
        for editorial_note_row in editorial_note_rows
        if APPENDIX_LINK_CAPTION_RE.match(editorial_note_row.transcript)
    ]
    return sorted(
        transcript_row.id
        for transcript_row in procedural_rows + caption_rows
        if transcript_row.id not in excluded_speech_ids
    )


def get_other_member_id(
    speaker_id_to_speaker: dict[int, Speaker],
    parliament_number: int,
    original_speaker: Speaker,
    fraction: float,
) -> Optional[int]:
    other_member_ids = sorted(
        speaker_id
        for speaker_id, speaker in speaker_id_to_speaker.items()
        if speaker.is_member
        and speaker.parliament_number == parliament_number
        and speaker.name != original_speaker.name
        and (
            speaker.person_id is None or speaker.person_id != original_speaker.person_id
        )
    )
    if not other_member_ids:
        return None
    return other_member_ids[int(fraction * len(other_member_ids))]


def write_plant_files(
    plant_rows: HandCheckSnapshotRows,
    plant_key: HandCheckPlantKey,
    plants_path: Path,
    key_path: Path,
    hash_path: Path,
) -> str:
    with plants_path.open("x", encoding="utf-8") as plants_file:
        plants_file.write(plant_rows.model_dump_json(indent=2))
    key_bytes = plant_key.model_dump_json(indent=2).encode("utf-8")
    digest = hashlib.sha256(key_bytes).hexdigest()
    with key_path.open("xb") as key_file:
        key_file.write(key_bytes)
    with hash_path.open("x", encoding="utf-8") as hash_file:
        hash_file.write(f"{digest}\n")
    return digest


def build_snapshot_row(
    speech_snapshot_row: SpeechSnapshotRow,
    next_row: Optional[SpeechParseRow],
    speaker_label: Optional[str],
    speaker_id: int,
    transcript: str,
    lookups: CreditLookups,
) -> HandCheckSnapshotRow:
    speaker = lookups.speaker_id_to_speaker[speaker_id]
    return HandCheckSnapshotRow(
        speech_id=speech_snapshot_row.id,
        report_id=speech_snapshot_row.report_id,
        hansard_report_id=speech_snapshot_row.hansard_report_id,
        html_file_name=speech_snapshot_row.html_file_name,
        report_version=speech_snapshot_row.report_version,
        report_type=speech_snapshot_row.report_type,
        parliament_number=speech_snapshot_row.parliament_number,
        sitting_date=speech_snapshot_row.sitting_date,
        report_title=speech_snapshot_row.title,
        ordinal=speech_snapshot_row.ordinal,
        speaker=speaker_label,
        speaker_id=speaker_id,
        speaker_name=speaker.name,
        person_name=None
        if speaker.person_id is None
        else lookups.person_id_to_canonical_name[speaker.person_id],
        kind=speech_snapshot_row.kind,
        transcript=transcript,
        next_speaker=None if next_row is None else next_row.speaker,
        next_transcript=None if next_row is None else next_row.transcript,
    )


def plant_wrong_member(
    source: SpeechSnapshotRow,
    speaker_id: int,
    next_row: Optional[SpeechParseRow],
    fraction: float,
    lookups: CreditLookups,
) -> Optional[PlantedRow]:
    original_speaker = lookups.speaker_id_to_speaker[speaker_id]
    other_member_id = get_other_member_id(
        lookups.speaker_id_to_speaker,
        source.parliament_number,
        original_speaker,
        fraction,
    )
    if other_member_id is None:
        return None
    return PlantedRow(
        snapshot_row=build_snapshot_row(
            source,
            next_row,
            source.speaker,
            other_member_id,
            source.transcript,
            lookups,
        ),
        plant=HandCheckPlant(
            speech_id=source.id,
            kind=HandCheckPlantKind.WRONG_MEMBER,
            original=original_speaker.name,
            planted=lookups.speaker_id_to_speaker[other_member_id].name,
        ),
    )


def plant_credited_non_speech_line(
    source: SpeechSnapshotRow,
    report_rows: list[SpeechParseRow],
    next_row: Optional[SpeechParseRow],
    lookups: CreditLookups,
) -> Optional[PlantedRow]:
    credited_row = get_nearest_credited_row_above(report_rows, source.ordinal)
    if credited_row is None:
        return None
    if credited_row.speaker_id is None:
        return None
    if is_role_label(credited_row.speaker):
        return None
    return PlantedRow(
        snapshot_row=build_snapshot_row(
            source,
            next_row,
            credited_row.speaker,
            credited_row.speaker_id,
            source.transcript,
            lookups,
        ),
        plant=HandCheckPlant(
            speech_id=source.id,
            kind=HandCheckPlantKind.CREDITED_NON_SPEECH_LINE,
            original="",
            planted=lookups.speaker_id_to_speaker[credited_row.speaker_id].name,
        ),
    )


def _get_planted_row(
    kind: HandCheckPlantKind,
    speech_id: int,
    generator: random.Random,
    session: Session,
    lookups: CreditLookups,
) -> Optional[PlantedRow]:
    [source] = CRUDSpeech(session).get_snapshot_rows_by_ids([speech_id])
    report_rows = CRUDSpeech(session).get_parse_rows_by_report_ids([source.report_id])
    next_row = get_next_row(report_rows, source.id)
    if kind == HandCheckPlantKind.CREDITED_NON_SPEECH_LINE:
        return plant_credited_non_speech_line(source, report_rows, next_row, lookups)
    speaker_id = source.speaker_id
    if speaker_id is None or is_role_label(source.speaker):
        return None
    return plant_wrong_member(source, speaker_id, next_row, generator.random(), lookups)


def _pop_planted_row(
    kind: HandCheckPlantKind,
    candidate_speech_ids: list[int],
    generator: random.Random,
    session: Session,
    lookups: CreditLookups,
) -> PlantedRow:
    while candidate_speech_ids:
        speech_id = candidate_speech_ids.pop(
            int(generator.random() * len(candidate_speech_ids))
        )
        planted_row = _get_planted_row(kind, speech_id, generator, session, lookups)
        if planted_row is not None:
            return planted_row
    raise HansardHandCheckError(f"No row is left to plant a {kind} error in")


def build_hand_check_plants(
    round_number: int,
    snapshot_path: Path,
    previous_plants_path: Optional[Path],
    plants_path: Path,
    key_path: Path,
    hash_path: Path,
) -> None:
    excluded_speech_ids = {
        snapshot_row.speech_id
        for snapshot_row in HandCheckSnapshot.model_validate_json(
            snapshot_path.read_text(encoding="utf-8")
        ).rows
    }
    if previous_plants_path is not None:
        excluded_speech_ids |= {
            previous_plant_row.speech_id
            for previous_plant_row in HandCheckSnapshotRows.model_validate_json(
                previous_plants_path.read_text(encoding="utf-8")
            ).root
        }
    generator = random.Random(_PLANT_ROUND_TO_SEED[round_number])
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_PLANT_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        lookups = CreditLookups(
            speaker_id_to_speaker={
                speaker.id: speaker
                for speaker in CRUDSpeaker(session).get_all()
                if speaker.id is not None
            },
            person_id_to_canonical_name={
                person.id: person.canonical_name
                for person in CRUDPerson(session).get_all()
                if person.id is not None
            },
        )
        credited_speech_ids = sorted(
            frame_row.id
            for frame_row in CRUDSpeech(session).get_frame_rows_by_speaker_id_not_null()
            if frame_row.id not in excluded_speech_ids
        )
        non_speech_speech_ids = get_non_speech_speech_ids(
            CRUDSpeech(session).get_transcript_rows_by_speaker_id_null_and_kind(
                SpeechKind.PROCEDURAL
            ),
            CRUDSpeech(session).get_transcript_rows_by_speaker_id_null_and_kind(
                SpeechKind.EDITORIAL_NOTE
            ),
            excluded_speech_ids,
        )
        planted_rows: list[PlantedRow] = []
        for kind, count in _PLANT_KIND_TO_COUNT.items():
            candidate_speech_ids = (
                non_speech_speech_ids
                if kind == HandCheckPlantKind.CREDITED_NON_SPEECH_LINE
                else credited_speech_ids
            )
            for _ in range(count):
                planted_rows.append(
                    _pop_planted_row(
                        kind, candidate_speech_ids, generator, session, lookups
                    )
                )

    digest = write_plant_files(
        HandCheckSnapshotRows(
            [planted_row.snapshot_row for planted_row in planted_rows]
        ),
        HandCheckPlantKey(
            round_number=round_number,
            plants=[planted_row.plant for planted_row in planted_rows],
        ),
        plants_path,
        key_path,
        hash_path,
    )
    logger.info(
        f"Round {round_number}: {len(planted_rows)} planted rows, key SHA-256 {digest}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build one round of sealed planted-error rows for the human hand check, read only"
    )
    parser.add_argument(
        "--round",
        dest="round_number",
        type=int,
        choices=sorted(_PLANT_ROUND_TO_SEED),
        required=True,
        help="1 for the first set of plants, 2 for the rerun's fresh set",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        required=True,
        help="the main snapshot file; none of its rows is planted",
    )
    parser.add_argument(
        "--previous-plants",
        type=Path,
        help="the plants file of the earlier round; its rows are left out; required from round 2",
    )
    parser.add_argument(
        "--plants-output",
        type=Path,
        required=True,
        help="the planted snapshot rows; written with mode x, so it may not exist yet",
    )
    parser.add_argument(
        "--key-output",
        type=Path,
        required=True,
        help="kept outside every reader batch directory; written with mode x, so it may not exist yet",
    )
    parser.add_argument(
        "--hash-output",
        type=Path,
        required=True,
        help="the one-line SHA-256 file to commit before any reader starts; written with mode x, so it may not exist yet",
    )
    arguments = parser.parse_args()
    if (
        arguments.round_number != _FIRST_ROUND_NUMBER
        and arguments.previous_plants is None
    ):
        parser.error("--previous-plants is required from round 2")
    build_hand_check_plants(
        arguments.round_number,
        arguments.snapshot,
        arguments.previous_plants,
        arguments.plants_output,
        arguments.key_output,
        arguments.hash_output,
    )
