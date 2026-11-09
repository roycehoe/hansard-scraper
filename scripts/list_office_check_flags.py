import argparse
import hashlib
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from enums import OfficeCheckVerdictKind
from exceptions import HansardOfficeCheckError
from logs import logger
from schemas.office_check import (
    OfficeCheckFlag,
    OfficeCheckFlags,
    OfficeCheckPacket,
    OfficeCheckPackets,
    OfficeCheckPlantKey,
    OfficeCheckVerdict,
)

_VERDICTS_FILE_NAME = "verdicts.jsonl"
_LISTED_PACKET_ID_COUNT = 5
_SONNET_READER = "Sonnet"
_OPUS_READER = "Opus"


def _get_verdict(path: Path, line_number: int, line: str) -> OfficeCheckVerdict:
    try:
        return OfficeCheckVerdict.model_validate_json(line)
    except ValidationError as error:
        raise HansardOfficeCheckError(
            f"{path}:{line_number} is not a valid verdict line: {error}"
        ) from error


def _get_verdicts(verdicts_directory: Path) -> list[OfficeCheckVerdict]:
    verdicts: list[OfficeCheckVerdict] = []
    for path in sorted(verdicts_directory.rglob(_VERDICTS_FILE_NAME)):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            verdicts.append(_get_verdict(path, line_number, line))
    return verdicts


def _get_packet_id_to_verdict(
    packets: list[OfficeCheckPacket],
    verdicts: list[OfficeCheckVerdict],
    reader: str,
) -> dict[str, OfficeCheckVerdict]:
    packet_ids = [packet.packet_id for packet in packets]
    verdict_counts = Counter(verdict.packet_id for verdict in verdicts)
    unknown_packet_ids = sorted(verdict_counts.keys() - set(packet_ids))
    if unknown_packet_ids:
        raise HansardOfficeCheckError(
            f"{reader} wrote verdicts for {len(unknown_packet_ids)} packets that do not exist, first {unknown_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    repeated_packet_ids = sorted(
        packet_id for packet_id, count in verdict_counts.items() if count > 1
    )
    if repeated_packet_ids:
        raise HansardOfficeCheckError(
            f"{reader} wrote more than one verdict for {len(repeated_packet_ids)} packets, first {repeated_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    missing_packet_ids = [
        packet_id for packet_id in packet_ids if packet_id not in verdict_counts
    ]
    if missing_packet_ids:
        raise HansardOfficeCheckError(
            f"{reader} has no verdict for {len(missing_packet_ids)} packets, first {missing_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    return {verdict.packet_id: verdict for verdict in verdicts}


def _validate_can_open_plant_key(
    plant_key_bytes: bytes, committed_sha256: str, packets: list[OfficeCheckPacket]
) -> OfficeCheckPlantKey:
    key_sha256 = hashlib.sha256(plant_key_bytes).hexdigest()
    if key_sha256 != committed_sha256:
        raise HansardOfficeCheckError(
            f"The plant key hashes to {key_sha256}, the hash file holds {committed_sha256}"
        )
    plant_key = OfficeCheckPlantKey.model_validate_json(plant_key_bytes)
    unknown_planted_packet_ids = sorted(
        set(plant_key.planted_packet_ids) - {packet.packet_id for packet in packets}
    )
    if unknown_planted_packet_ids:
        raise HansardOfficeCheckError(
            f"The plant key names {len(unknown_planted_packet_ids)} packets that do not exist, first {unknown_planted_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    return plant_key


def _validate_can_write_flags(output_path: Path, summary_path: Path) -> None:
    if output_path.exists():
        raise HansardOfficeCheckError(
            f"{output_path} exists; pass a path that does not"
        )
    if summary_path.exists():
        raise HansardOfficeCheckError(
            f"{summary_path} exists; pass a path that does not"
        )


def _get_summary_lines(
    plant_key: OfficeCheckPlantKey,
    packets: list[OfficeCheckPacket],
    flags: list[OfficeCheckFlag],
    reader_to_packet_id_to_verdict: dict[str, dict[str, OfficeCheckVerdict]],
) -> list[str]:
    planted_packet_ids = set(plant_key.planted_packet_ids)
    lines = [
        f"Rule: {plant_key.rule}",
        f"Round: {plant_key.round_number}",
        f"Packets: {len(packets)}, sampled {len(packets) - len(planted_packet_ids)}, planted {len(planted_packet_ids)}",
        f"Flags: {len(flags)}",
    ]
    group_to_flag_count = Counter(flag.group for flag in flags)
    for group in sorted(group_to_flag_count):
        lines.append(f"Flags in group {group}: {group_to_flag_count[group]}")
    for reader, packet_id_to_verdict in reader_to_packet_id_to_verdict.items():
        verdict_to_count = Counter(
            verdict.verdict for verdict in packet_id_to_verdict.values()
        )
        lines.append(
            f"{reader} verdicts: "
            + ", ".join(
                f"{verdict_kind} {verdict_to_count[verdict_kind]}"
                for verdict_kind in OfficeCheckVerdictKind
            )
        )
        caught_packet_ids = sorted(
            packet_id
            for packet_id in planted_packet_ids
            if packet_id_to_verdict[packet_id].verdict != OfficeCheckVerdictKind.RIGHT
        )
        missed_packet_ids = sorted(planted_packet_ids - set(caught_packet_ids))
        lines.append(
            f"{reader} caught {len(caught_packet_ids)} of {len(planted_packet_ids)} plants; missed {missed_packet_ids}"
        )
    return lines


def list_office_check_flags(
    records_path: Path,
    sonnet_verdicts_directory: Path,
    opus_verdicts_directory: Path,
    plant_key_path: Path,
    plant_key_hash_path: Path,
    output_path: Path,
    summary_path: Path,
) -> None:
    _validate_can_write_flags(output_path, summary_path)
    packets = OfficeCheckPackets.model_validate_json(
        records_path.read_text(encoding="utf-8")
    ).root
    plant_key = _validate_can_open_plant_key(
        plant_key_path.read_bytes(),
        plant_key_hash_path.read_text(encoding="utf-8").strip(),
        packets,
    )
    sonnet_packet_id_to_verdict = _get_packet_id_to_verdict(
        packets, _get_verdicts(sonnet_verdicts_directory), _SONNET_READER
    )
    opus_packet_id_to_verdict = _get_packet_id_to_verdict(
        packets, _get_verdicts(opus_verdicts_directory), _OPUS_READER
    )
    planted_packet_ids = set(plant_key.planted_packet_ids)
    flags = [
        OfficeCheckFlag(
            packet_id=packet.packet_id,
            rule=packet.rule,
            group=packet.group,
            source_text=packet.source_text,
            data_says=packet.data_says,
            made_by=packet.made_by,
            row_key=packet.row_key,
            sonnet_verdict=sonnet_packet_id_to_verdict[packet.packet_id].verdict,
            opus_verdict=opus_packet_id_to_verdict[packet.packet_id].verdict,
            sonnet_note=sonnet_packet_id_to_verdict[packet.packet_id].note,
            opus_note=opus_packet_id_to_verdict[packet.packet_id].note,
        )
        for packet in packets
        if packet.packet_id not in planted_packet_ids
        and (
            sonnet_packet_id_to_verdict[packet.packet_id].verdict
            != OfficeCheckVerdictKind.RIGHT
            or opus_packet_id_to_verdict[packet.packet_id].verdict
            != OfficeCheckVerdictKind.RIGHT
        )
    ]
    summary_lines = _get_summary_lines(
        plant_key,
        packets,
        flags,
        {
            _SONNET_READER: sonnet_packet_id_to_verdict,
            _OPUS_READER: opus_packet_id_to_verdict,
        },
    )
    with output_path.open("x", encoding="utf-8") as output_file:
        output_file.write(OfficeCheckFlags(flags).model_dump_json(indent=1))
    with summary_path.open("x", encoding="utf-8") as summary_file:
        summary_file.write("\n".join(summary_lines) + "\n")
    for summary_line in summary_lines:
        logger.info(summary_line)
    logger.info(f"Wrote {output_path} and {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List the sampled office rows either reader did not mark RIGHT, and score the readers against the planted errors"
    )
    parser.add_argument(
        "--records", type=Path, required=True, help="records.json of the draw"
    )
    parser.add_argument(
        "--sonnet-verdicts",
        type=Path,
        required=True,
        help="a directory of verdicts.jsonl files",
    )
    parser.add_argument(
        "--opus-verdicts",
        type=Path,
        required=True,
        help="a directory of verdicts.jsonl files",
    )
    parser.add_argument(
        "--key", type=Path, required=True, help="plant-key.json of the draw"
    )
    parser.add_argument(
        "--key-hash",
        type=Path,
        required=True,
        help="plant-key.sha256 of the draw, kept apart from the key",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="where to write the flag list as JSON",
    )
    parser.add_argument(
        "--summary", type=Path, required=True, help="where to write the summary lines"
    )
    arguments = parser.parse_args()
    list_office_check_flags(
        arguments.records,
        arguments.sonnet_verdicts,
        arguments.opus_verdicts,
        arguments.key,
        arguments.key_hash,
        arguments.output,
        arguments.summary,
    )
