import argparse
import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from enums import AttachedFileCheckAnswer, AttachedFileCheckPlantKind, ParagraphTieRule
from exceptions import HansardAttachedFileError
from logs import logger
from schemas.attached_file_check import (
    AttachedFileCheckFlag,
    AttachedFileCheckFlags,
    AttachedFileCheckKey,
    AttachedFileCheckPacket,
    AttachedFileCheckPackets,
    AttachedFileCheckPlant,
    AttachedFileCheckVerdict,
)

_VERDICTS_FILE_NAME = "verdicts.jsonl"
_LISTED_PACKET_ID_COUNT = 5
_SONNET_NAME = "Sonnet"
_OPUS_NAME = "Opus"


@dataclass(frozen=True)
class _PlantGroup:
    label: str
    plants: list[AttachedFileCheckPlant]


def _validate_can_open_key(key_bytes: bytes, committed_sha256: str) -> None:
    key_sha256 = hashlib.sha256(key_bytes).hexdigest()
    if key_sha256 != committed_sha256:
        raise HansardAttachedFileError(
            f"The key hashes to {key_sha256}, not the committed {committed_sha256}"
        )


def _validate_can_write_flags(output_path: Path, summary_path: Path) -> None:
    for path in (output_path, summary_path):
        if path.exists():
            raise HansardAttachedFileError(f"{path} already exists")


def _get_verdicts(verdicts_directory: Path) -> list[AttachedFileCheckVerdict]:
    verdicts = []
    for path in sorted(verdicts_directory.rglob(_VERDICTS_FILE_NAME)):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            try:
                verdicts.append(AttachedFileCheckVerdict.model_validate_json(line))
            except ValidationError as error:
                raise HansardAttachedFileError(
                    f"{path}:{line_number} is not a valid verdict line: {error}"
                ) from error
    return verdicts


def _get_packet_id_to_verdict(
    packets: list[AttachedFileCheckPacket],
    verdicts: list[AttachedFileCheckVerdict],
    reader_name: str,
) -> dict[str, AttachedFileCheckVerdict]:
    packet_ids = [packet.packet_id for packet in packets]
    verdict_counts = Counter(verdict.packet_id for verdict in verdicts)
    unknown_packet_ids = sorted(verdict_counts.keys() - set(packet_ids))
    if unknown_packet_ids:
        raise HansardAttachedFileError(
            f"{reader_name} wrote verdicts for {len(unknown_packet_ids)} packets that do not exist, first {unknown_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    repeated_packet_ids = sorted(
        packet_id for packet_id, count in verdict_counts.items() if count > 1
    )
    if repeated_packet_ids:
        raise HansardAttachedFileError(
            f"{reader_name} wrote more than one verdict for {len(repeated_packet_ids)} packets, first {repeated_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    missing_packet_ids = [
        packet_id for packet_id in packet_ids if packet_id not in verdict_counts
    ]
    if missing_packet_ids:
        raise HansardAttachedFileError(
            f"{reader_name} has no verdict for {len(missing_packet_ids)} packets, first {missing_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    packet_id_to_verdict = {verdict.packet_id: verdict for verdict in verdicts}
    disagreeing_packet_ids = [
        packet.packet_id
        for packet in packets
        if (packet.file_kind is None)
        != (packet_id_to_verdict[packet.packet_id].file_answer is None)
    ]
    if disagreeing_packet_ids:
        raise HansardAttachedFileError(
            f"{reader_name} gave a file answer that disagrees with the packet for {len(disagreeing_packet_ids)} packets, first {disagreeing_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    return packet_id_to_verdict


def _is_plant_caught(
    plant: AttachedFileCheckPlant, verdict: AttachedFileCheckVerdict
) -> bool:
    if plant.kind == AttachedFileCheckPlantKind.FILE:
        return verdict.file_answer != AttachedFileCheckAnswer.RIGHT
    return verdict.paragraph_answer != AttachedFileCheckAnswer.RIGHT


def _is_verdict_flagging(verdict: AttachedFileCheckVerdict) -> bool:
    if verdict.paragraph_answer != AttachedFileCheckAnswer.RIGHT:
        return True
    return (
        verdict.file_answer is not None
        and verdict.file_answer != AttachedFileCheckAnswer.RIGHT
    )


def _get_plant_groups(plants: list[AttachedFileCheckPlant]) -> list[_PlantGroup]:
    return [
        _PlantGroup(
            "file plants",
            [
                plant
                for plant in plants
                if plant.kind == AttachedFileCheckPlantKind.FILE
            ],
        ),
        _PlantGroup(
            "paragraph plants on a row holding the link words",
            [
                plant
                for plant in plants
                if plant.kind == AttachedFileCheckPlantKind.PARAGRAPH
                and plant.is_row_holding_link_words is True
            ],
        ),
        _PlantGroup(
            "paragraph plants on a row without the link words",
            [
                plant
                for plant in plants
                if plant.kind == AttachedFileCheckPlantKind.PARAGRAPH
                and plant.is_row_holding_link_words is False
            ],
        ),
    ]


def _get_recall_lines(
    reader_name: str,
    plant_groups: list[_PlantGroup],
    packet_id_to_verdict: dict[str, AttachedFileCheckVerdict],
) -> list[str]:
    lines = [f"{reader_name} recall"]
    for plant_group in plant_groups:
        missed_plants = [
            plant
            for plant in plant_group.plants
            if not _is_plant_caught(plant, packet_id_to_verdict[plant.packet_id])
        ]
        lines.append(
            f"  {plant_group.label}: caught {len(plant_group.plants) - len(missed_plants)} of {len(plant_group.plants)}"
        )
        lines.extend(f"    missed packet {plant.packet_id}" for plant in missed_plants)
    return lines


def _get_flags(
    packets: list[AttachedFileCheckPacket],
    plant_packet_ids: set[str],
    round_number: int,
    packet_id_to_sonnet_verdict: dict[str, AttachedFileCheckVerdict],
    packet_id_to_opus_verdict: dict[str, AttachedFileCheckVerdict],
) -> list[AttachedFileCheckFlag]:
    flags = []
    for packet in packets:
        if packet.packet_id in plant_packet_ids:
            continue
        sonnet_verdict = packet_id_to_sonnet_verdict[packet.packet_id]
        opus_verdict = packet_id_to_opus_verdict[packet.packet_id]
        if not _is_verdict_flagging(sonnet_verdict) and not _is_verdict_flagging(
            opus_verdict
        ):
            continue
        flags.append(
            AttachedFileCheckFlag(
                packet_id=packet.packet_id,
                round_number=round_number,
                sprs_report_id=packet.sprs_report_id,
                pointer_ordinal=packet.pointer_ordinal,
                speech_ordinal=packet.speech_ordinal,
                attached_file_id=packet.attached_file_id,
                link_words=packet.link_words,
                source_paragraph=packet.source_paragraph,
                row_transcript=packet.row_transcript,
                file_title=packet.file_title,
                paragraph_tie_rule=packet.paragraph_tie_rule,
                sonnet=sonnet_verdict,
                opus=opus_verdict,
            )
        )
    return flags


def list_attached_file_flags(
    packets_path: Path,
    key_path: Path,
    key_hash_path: Path,
    sonnet_verdicts_directory: Path,
    opus_verdicts_directory: Path,
    output_path: Path,
    summary_path: Path,
) -> None:
    _validate_can_write_flags(output_path, summary_path)
    key_bytes = key_path.read_bytes()
    _validate_can_open_key(key_bytes, key_hash_path.read_text(encoding="utf-8").strip())
    key = AttachedFileCheckKey.model_validate_json(key_bytes)
    packets = AttachedFileCheckPackets.model_validate_json(
        packets_path.read_text(encoding="utf-8")
    ).root
    packet_id_to_sonnet_verdict = _get_packet_id_to_verdict(
        packets, _get_verdicts(sonnet_verdicts_directory), _SONNET_NAME
    )
    packet_id_to_opus_verdict = _get_packet_id_to_verdict(
        packets, _get_verdicts(opus_verdicts_directory), _OPUS_NAME
    )
    plant_packet_ids = {plant.packet_id for plant in key.plants}
    unknown_plant_packet_ids = sorted(
        plant_packet_ids - {packet.packet_id for packet in packets}
    )
    if unknown_plant_packet_ids:
        raise HansardAttachedFileError(
            f"{len(unknown_plant_packet_ids)} planted packets are not in the packets file, first {unknown_plant_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    flags = _get_flags(
        packets,
        plant_packet_ids,
        key.round_number,
        packet_id_to_sonnet_verdict,
        packet_id_to_opus_verdict,
    )

    plant_groups = _get_plant_groups(key.plants)
    tie_rule_to_flag_count = Counter(flag.paragraph_tie_rule for flag in flags)
    summary_lines = [
        f"Attached file check flags, round {key.round_number}",
        f"Packets: {len(packets)}, of which {len(key.plants)} planted",
        f"Flags: {len(flags)}",
        "Flags by tier",
        *(
            f"  {tie_rule.value}: {tie_rule_to_flag_count[tie_rule]}"
            for tie_rule in ParagraphTieRule
        ),
        *_get_recall_lines(_SONNET_NAME, plant_groups, packet_id_to_sonnet_verdict),
        *_get_recall_lines(_OPUS_NAME, plant_groups, packet_id_to_opus_verdict),
    ]
    with output_path.open("x", encoding="utf-8") as output_file:
        output_file.write(AttachedFileCheckFlags(flags).model_dump_json(indent=2))
    with summary_path.open("x", encoding="utf-8") as summary_file:
        summary_file.write("\n".join(summary_lines) + "\n")
    logger.info(
        f"Round {key.round_number}: {len(flags)} flags from {len(packets)} packets"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List the attached file check's flags from the readers' verdicts, no database needed"
    )
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--key-hash", type=Path, required=True)
    parser.add_argument("--sonnet-verdicts", type=Path, required=True)
    parser.add_argument("--opus-verdicts", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="the flags file; may not exist yet"
    )
    parser.add_argument(
        "--summary",
        type=Path,
        required=True,
        help="the summary file; may not exist yet",
    )
    arguments = parser.parse_args()
    list_attached_file_flags(
        arguments.packets,
        arguments.key,
        arguments.key_hash,
        arguments.sonnet_verdicts,
        arguments.opus_verdicts,
        arguments.output,
        arguments.summary,
    )
