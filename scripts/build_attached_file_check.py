import argparse
import hashlib
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.attached_file import CRUDAttachedFile
from crud.attached_file_pointer import (
    AttachedFilePointerCheckRow,
    CRUDAttachedFilePointer,
)
from crud.report import CRUDReport
from crud.speech import CRUDSpeech, SpeechRow
from database.attached_file import AttachedFile
from database.init import build_read_only_engine
from enums import AttachedFileCheckPlantKind, ParagraphTieRule
from exceptions import HansardAttachedFileError
from logs import logger
from schemas.attached_file_check import (
    AttachedFileCheckKey,
    AttachedFileCheckPacket,
    AttachedFileCheckPackets,
    AttachedFileCheckPlant,
)
from services.attached_file import (
    get_pointer_paragraph_text,
    is_paragraph_tie_stale,
)
from settings import settings

_ROUND_TO_SEED = {1: 20_261_201, 2: 20_261_202, 3: 20_261_203}
_GROUP_SAMPLE_SIZE = 50
_PLANTS_PER_KIND = 15
_MAX_PACKETS_PER_BATCH = 50
_MAX_CHARACTERS_PER_BATCH = 80_000
_READER_NAMES = ("sonnet", "opus")
_YEARS_PER_DECADE = 10
_LOOKUP_BATCH_SIZE = 200
_PACKET_ID_BITS = 48
_PACKET_ID_LENGTH = 12
_RECORDS_DIRECTORY_NAME = "records"
_BATCHES_DIRECTORY_NAME = "batches"
_PACKETS_FILE_NAME = "packets.json"
_KEY_FILE_NAME = "key.json"
_KEY_HASH_FILE_NAME = "key.sha256"
_NO_VALUE_TEXT = "(none)"
_BATCH_LEGEND = (
    "For each packet, write one JSON line with packet_id, paragraph_answer, "
    "file_answer and note.\n\n"
    "paragraph_answer: RIGHT when the speech row below is the row the source "
    "paragraph's link sits in, WRONG when it is another row, UNSURE when you "
    "cannot tell.\n\n"
    "file_answer: when a file is shown, RIGHT when it is the file the link "
    "names, WRONG when it is another file, UNSURE when you cannot tell. "
    "When no file is shown, write null.\n\n"
    "A long source paragraph is cut to the text either side of the link, so it "
    "may start or end in the middle of a word.\n"
)


@dataclass(frozen=True)
class _CheckedTie:
    check_row: AttachedFilePointerCheckRow
    speech_ordinal: int
    attached_file_id: Optional[int]
    plant_kind: Optional[AttachedFileCheckPlantKind]
    is_row_holding_link_words: Optional[bool]


def _get_sort_key(check_row: AttachedFilePointerCheckRow) -> tuple[str, int]:
    return (check_row.sprs_report_id, check_row.ordinal)


def _get_group_key(check_row: AttachedFilePointerCheckRow) -> tuple[str, int, str]:
    decade = check_row.sitting_date.year // _YEARS_PER_DECADE * _YEARS_PER_DECADE
    if check_row.paragraph_tie_rule == ParagraphTieRule.ONLY_OCCURRENCE:
        return (check_row.paragraph_tie_rule.value, decade, "")
    return (check_row.paragraph_tie_rule.value, decade, check_row.report_type)


def _draw_sample(
    check_rows: list[AttachedFilePointerCheckRow], generator: random.Random
) -> list[AttachedFilePointerCheckRow]:
    group_key_to_check_rows: defaultdict[
        tuple[str, int, str], list[AttachedFilePointerCheckRow]
    ] = defaultdict(list)
    for check_row in check_rows:
        group_key_to_check_rows[_get_group_key(check_row)].append(check_row)
    sample_rows: list[AttachedFilePointerCheckRow] = []
    for group_key in sorted(group_key_to_check_rows):
        group_rows = sorted(group_key_to_check_rows[group_key], key=_get_sort_key)
        group_sample_size = min(_GROUP_SAMPLE_SIZE, len(group_rows))
        sample_rows.extend(generator.sample(group_rows, group_sample_size))
        logger.info(
            f"Group {group_key}: {len(group_rows):,} rows, {group_sample_size:,} sampled"
        )
    return sample_rows


def _get_report_ids_with_many_speech_rows(
    session: Session, report_ids: list[int]
) -> set[int]:
    many_report_ids: set[int] = set()
    for start in range(0, len(report_ids), _LOOKUP_BATCH_SIZE):
        speech_rows = CRUDSpeech(session).get_rows_by_report_ids(
            report_ids[start : start + _LOOKUP_BATCH_SIZE]
        )
        report_id_to_row_count = Counter(
            speech_row.report_id for speech_row in speech_rows
        )
        many_report_ids.update(
            report_id
            for report_id, row_count in report_id_to_row_count.items()
            if row_count > 1
        )
    return many_report_ids


def _get_report_id_to_speech_rows(
    session: Session, report_ids: list[int]
) -> dict[int, list[SpeechRow]]:
    report_id_to_speech_rows: dict[int, list[SpeechRow]] = defaultdict(list)
    for start in range(0, len(report_ids), _LOOKUP_BATCH_SIZE):
        for speech_row in CRUDSpeech(session).get_rows_by_report_ids(
            report_ids[start : start + _LOOKUP_BATCH_SIZE]
        ):
            report_id_to_speech_rows[speech_row.report_id].append(speech_row)
    return report_id_to_speech_rows


def _get_sitting_id_to_attached_files(
    session: Session, attached_file_ids: list[int]
) -> dict[int, list[AttachedFile]]:
    sitting_ids: set[int] = set()
    for start in range(0, len(attached_file_ids), _LOOKUP_BATCH_SIZE):
        sitting_ids.update(
            attached_file.sitting_id
            for attached_file in CRUDAttachedFile(session).get_by_ids(
                attached_file_ids[start : start + _LOOKUP_BATCH_SIZE]
            )
        )
    sorted_sitting_ids = sorted(sitting_ids)
    sitting_id_to_attached_files: dict[int, list[AttachedFile]] = defaultdict(list)
    for start in range(0, len(sorted_sitting_ids), _LOOKUP_BATCH_SIZE):
        for attached_file in CRUDAttachedFile(session).get_by_sitting_ids(
            sorted_sitting_ids[start : start + _LOOKUP_BATCH_SIZE]
        ):
            sitting_id_to_attached_files[attached_file.sitting_id].append(attached_file)
    return sitting_id_to_attached_files


def _plant_paragraph(
    check_row: AttachedFilePointerCheckRow,
    speech_rows: list[SpeechRow],
    generator: random.Random,
) -> _CheckedTie:
    other_rows = [
        speech_row
        for speech_row in speech_rows
        if speech_row.ordinal != check_row.speech_ordinal
    ]
    rows_holding_link_words = [
        other_row
        for other_row in other_rows
        if not is_paragraph_tie_stale(check_row.printed_text, other_row.transcript)
    ]
    planted_row = generator.choice(rows_holding_link_words or other_rows)
    return _CheckedTie(
        check_row=check_row,
        speech_ordinal=planted_row.ordinal,
        attached_file_id=check_row.attached_file_id,
        plant_kind=AttachedFileCheckPlantKind.PARAGRAPH,
        is_row_holding_link_words=bool(rows_holding_link_words),
    )


def _plant_file(
    check_row: AttachedFilePointerCheckRow,
    true_file: AttachedFile,
    sitting_files: list[AttachedFile],
    generator: random.Random,
) -> _CheckedTie:
    other_files = [
        sitting_file
        for sitting_file in sitting_files
        if sitting_file.id != true_file.id
    ]
    other_files_of_kind = [
        other_file for other_file in other_files if other_file.kind == true_file.kind
    ]
    planted_file = generator.choice(other_files_of_kind or other_files)
    return _CheckedTie(
        check_row=check_row,
        speech_ordinal=check_row.speech_ordinal,
        attached_file_id=planted_file.id,
        plant_kind=AttachedFileCheckPlantKind.FILE,
        is_row_holding_link_words=None,
    )


def _get_packet_ids(count: int, generator: random.Random) -> list[str]:
    packet_ids: list[str] = []
    seen_packet_ids: set[str] = set()
    while len(packet_ids) < count:
        packet_id = f"{generator.getrandbits(_PACKET_ID_BITS):0{_PACKET_ID_LENGTH}x}"
        if packet_id in seen_packet_ids:
            continue
        seen_packet_ids.add(packet_id)
        packet_ids.append(packet_id)
    return packet_ids


def _build_packet(
    packet_id: str,
    checked_tie: _CheckedTie,
    content: str,
    speech_row: SpeechRow,
    attached_file: Optional[AttachedFile],
) -> AttachedFileCheckPacket:
    check_row = checked_tie.check_row
    return AttachedFileCheckPacket(
        packet_id=packet_id,
        sprs_report_id=check_row.sprs_report_id,
        pointer_ordinal=check_row.ordinal,
        paragraph_tie_rule=check_row.paragraph_tie_rule,
        speech_ordinal=checked_tie.speech_ordinal,
        attached_file_id=checked_tie.attached_file_id,
        report_title=check_row.report_title,
        link_words=check_row.printed_text,
        source_paragraph=get_pointer_paragraph_text(content, check_row.ordinal),
        row_speaker=speech_row.speaker,
        row_transcript=speech_row.transcript,
        file_kind=None if attached_file is None else attached_file.kind,
        file_title=None if attached_file is None else attached_file.printed_title,
    )


def _render_packet(packet: AttachedFileCheckPacket) -> str:
    return "\n".join(
        [
            f"## Packet {packet.packet_id}",
            "",
            f"Report: {packet.report_title}",
            f"Link words: {packet.link_words}",
            f"Source paragraph: {packet.source_paragraph}",
            f"Speech row speaker: {packet.row_speaker or _NO_VALUE_TEXT}",
            f"Speech row text: {packet.row_transcript}",
            f"File kind: {_NO_VALUE_TEXT if packet.file_kind is None else packet.file_kind.value}",
            f"File title: {packet.file_title or _NO_VALUE_TEXT}",
            "",
            "",
        ]
    )


def _get_batches(rendered_packets: list[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    batch_character_count = 0
    for rendered_packet in rendered_packets:
        if (
            not batches
            or len(batches[-1]) >= _MAX_PACKETS_PER_BATCH
            or batch_character_count + len(rendered_packet) > _MAX_CHARACTERS_PER_BATCH
        ):
            batches.append([])
            batch_character_count = 0
        batches[-1].append(rendered_packet)
        batch_character_count += len(rendered_packet)
    return batches


def _validate_can_build_check(output_directory: Path) -> None:
    if output_directory.exists():
        raise HansardAttachedFileError(
            f"The output directory {output_directory} already exists"
        )


def _write_check_files(
    output_directory: Path,
    packets: list[AttachedFileCheckPacket],
    key: AttachedFileCheckKey,
    generator: random.Random,
) -> None:
    records_directory = output_directory / _RECORDS_DIRECTORY_NAME
    output_directory.mkdir(parents=True)
    records_directory.mkdir()
    (records_directory / _PACKETS_FILE_NAME).write_text(
        AttachedFileCheckPackets(packets).model_dump_json(indent=2), encoding="utf-8"
    )
    key_bytes = key.model_dump_json(indent=2).encode("utf-8")
    (records_directory / _KEY_FILE_NAME).write_bytes(key_bytes)
    (records_directory / _KEY_HASH_FILE_NAME).write_text(
        f"{hashlib.sha256(key_bytes).hexdigest()}\n", encoding="utf-8"
    )
    for reader_name in _READER_NAMES:
        reader_directory = output_directory / _BATCHES_DIRECTORY_NAME / reader_name
        reader_directory.mkdir(parents=True)
        shuffled_packets = list(packets)
        generator.shuffle(shuffled_packets)
        batches = _get_batches([_render_packet(packet) for packet in shuffled_packets])
        for batch_number, batch in enumerate(batches, start=1):
            (reader_directory / f"packets-{batch_number:03d}.md").write_text(
                _BATCH_LEGEND + "\n" + "".join(batch), encoding="utf-8"
            )


@dataclass(frozen=True)
class _PlantRows:
    paragraph_rows: list[AttachedFilePointerCheckRow]
    file_rows: list[AttachedFilePointerCheckRow]


def _draw_plant_rows(
    outside_rows: list[AttachedFilePointerCheckRow],
    many_report_ids: set[int],
    attached_file_id_to_attached_file: dict[int, AttachedFile],
    sitting_id_to_attached_files: dict[int, list[AttachedFile]],
    generator: random.Random,
) -> _PlantRows:
    paragraph_eligible_rows = [
        check_row
        for check_row in outside_rows
        if check_row.report_int_id in many_report_ids
    ]
    paragraph_rows = generator.sample(
        paragraph_eligible_rows, min(_PLANTS_PER_KIND, len(paragraph_eligible_rows))
    )
    paragraph_pointer_ids = {paragraph_row.id for paragraph_row in paragraph_rows}
    file_eligible_rows = [
        check_row
        for check_row in outside_rows
        if check_row.id not in paragraph_pointer_ids
        and check_row.attached_file_id is not None
        and len(
            sitting_id_to_attached_files[
                attached_file_id_to_attached_file[check_row.attached_file_id].sitting_id
            ]
        )
        > 1
    ]
    file_rows = generator.sample(
        file_eligible_rows, min(_PLANTS_PER_KIND, len(file_eligible_rows))
    )
    return _PlantRows(paragraph_rows, file_rows)


def _get_checked_ties(
    sample_rows: list[AttachedFilePointerCheckRow],
    plant_rows: _PlantRows,
    report_id_to_speech_rows: dict[int, list[SpeechRow]],
    attached_file_id_to_attached_file: dict[int, AttachedFile],
    sitting_id_to_attached_files: dict[int, list[AttachedFile]],
    generator: random.Random,
) -> list[_CheckedTie]:
    checked_ties = [
        _CheckedTie(
            check_row=sample_row,
            speech_ordinal=sample_row.speech_ordinal,
            attached_file_id=sample_row.attached_file_id,
            plant_kind=None,
            is_row_holding_link_words=None,
        )
        for sample_row in sample_rows
    ]
    checked_ties.extend(
        _plant_paragraph(
            paragraph_row,
            report_id_to_speech_rows[paragraph_row.report_int_id],
            generator,
        )
        for paragraph_row in plant_rows.paragraph_rows
    )
    for file_row in plant_rows.file_rows:
        if file_row.attached_file_id is None:
            continue
        true_file = attached_file_id_to_attached_file[file_row.attached_file_id]
        checked_ties.append(
            _plant_file(
                file_row,
                true_file,
                sitting_id_to_attached_files[true_file.sitting_id],
                generator,
            )
        )
    return checked_ties


def build_attached_file_check(round_number: int, output_directory: Path) -> None:
    _validate_can_build_check(output_directory)
    seed = _ROUND_TO_SEED[round_number]
    generator = random.Random(seed)
    with Session(build_read_only_engine(settings.database_url)) as session:
        check_rows = sorted(
            CRUDAttachedFilePointer(
                session
            ).get_check_rows_by_speech_ordinal_not_null(),
            key=_get_sort_key,
        )
        sample_rows = _draw_sample(check_rows, generator)
        sample_pointer_ids = {sample_row.id for sample_row in sample_rows}
        outside_rows = [
            check_row
            for check_row in check_rows
            if check_row.id not in sample_pointer_ids
        ]
        sitting_id_to_attached_files = _get_sitting_id_to_attached_files(
            session,
            sorted(
                {
                    check_row.attached_file_id
                    for check_row in check_rows
                    if check_row.attached_file_id is not None
                }
            ),
        )
        attached_file_id_to_attached_file = {
            attached_file.id: attached_file
            for attached_files in sitting_id_to_attached_files.values()
            for attached_file in attached_files
            if attached_file.id is not None
        }
        plant_rows = _draw_plant_rows(
            outside_rows,
            _get_report_ids_with_many_speech_rows(
                session, sorted({check_row.report_int_id for check_row in outside_rows})
            ),
            attached_file_id_to_attached_file,
            sitting_id_to_attached_files,
            generator,
        )
        logger.info(
            f"Round {round_number}, seed {seed}: {len(sample_rows):,} sampled, "
            f"{len(plant_rows.paragraph_rows)} paragraph plants, {len(plant_rows.file_rows)} file plants"
        )

        needed_report_ids = sorted(
            {
                check_row.report_int_id
                for check_row in [
                    *sample_rows,
                    *plant_rows.paragraph_rows,
                    *plant_rows.file_rows,
                ]
            }
        )
        report_id_to_speech_rows = _get_report_id_to_speech_rows(
            session, needed_report_ids
        )
        report_id_to_content = {
            report_row.id: report_row.content
            for start in range(0, len(needed_report_ids), _LOOKUP_BATCH_SIZE)
            for report_row in CRUDReport(session).get_attached_file_report_rows_by_ids(
                needed_report_ids[start : start + _LOOKUP_BATCH_SIZE]
            )
        }

    checked_ties = _get_checked_ties(
        sample_rows,
        plant_rows,
        report_id_to_speech_rows,
        attached_file_id_to_attached_file,
        sitting_id_to_attached_files,
        generator,
    )
    packets: list[AttachedFileCheckPacket] = []
    plants: list[AttachedFileCheckPlant] = []
    packet_id_to_pointer_id: dict[str, int] = {}
    for packet_id, checked_tie in zip(
        _get_packet_ids(len(checked_ties), generator), checked_ties, strict=True
    ):
        check_row = checked_tie.check_row
        content = report_id_to_content[check_row.report_int_id]
        if content is None:
            raise HansardAttachedFileError(
                f"Report {check_row.sprs_report_id} has no content for pointer {check_row.ordinal}"
            )
        [speech_row] = [
            report_speech_row
            for report_speech_row in report_id_to_speech_rows[check_row.report_int_id]
            if report_speech_row.ordinal == checked_tie.speech_ordinal
        ]
        packets.append(
            _build_packet(
                packet_id,
                checked_tie,
                content,
                speech_row,
                None
                if checked_tie.attached_file_id is None
                else attached_file_id_to_attached_file[checked_tie.attached_file_id],
            )
        )
        packet_id_to_pointer_id[packet_id] = check_row.id
        if checked_tie.plant_kind is not None:
            plants.append(
                AttachedFileCheckPlant(
                    packet_id=packet_id,
                    kind=checked_tie.plant_kind,
                    true_speech_ordinal=check_row.speech_ordinal,
                    true_attached_file_id=check_row.attached_file_id,
                    is_row_holding_link_words=checked_tie.is_row_holding_link_words,
                )
            )

    _write_check_files(
        output_directory,
        packets,
        AttachedFileCheckKey(
            round_number=round_number,
            seed=seed,
            packet_id_to_pointer_id=packet_id_to_pointer_id,
            plants=plants,
        ),
        generator,
    )
    logger.info(f"Wrote {len(packets):,} packets to {output_directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Draw the attached file accuracy sample and its planted errors, read only"
    )
    parser.add_argument(
        "--round",
        dest="round_number",
        type=int,
        choices=sorted(_ROUND_TO_SEED),
        required=True,
        help="the round, which picks the seed",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="the directory to create; it may not exist yet",
    )
    arguments = parser.parse_args()
    build_attached_file_check(arguments.round_number, arguments.output_directory)
