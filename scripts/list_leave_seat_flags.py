import argparse
import hashlib
from collections import Counter
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from enums import LeaveSeatCheckVerdict
from exceptions import HansardHandCheckError
from logs import logger
from schemas.leave_seat_check import (
    LeaveSeatCheckFlag,
    LeaveSeatCheckKeyEntry,
    LeaveSeatCheckPacket,
    LeaveSeatCheckVerdictLine,
)
from utils.leave_entry import YEAR_ORDER_BREAK_GROUP

_VERDICTS_FILE_NAME = "verdicts.jsonl"
_DEFAULT_OUTPUT_PATH = Path("plans/positions-over-time/flags/leave.json")
_SUMMARY_HEADER = (
    "group\tsample\tplants\tsonnet_plants_caught\topus_plants_caught\tflagged"
)
_KEY_ADAPTER = TypeAdapter(list[LeaveSeatCheckKeyEntry])
_FLAG_ADAPTER = TypeAdapter(list[LeaveSeatCheckFlag])


def _validate_can_open_key(key_bytes: bytes, committed_sha256: str) -> None:
    key_sha256 = hashlib.sha256(key_bytes).hexdigest()
    if key_sha256 != committed_sha256:
        raise HansardHandCheckError(
            f"The key hashes to {key_sha256}, not the committed {committed_sha256}"
        )


def _get_verdict_line(
    path: Path, line_number: int, line: str
) -> LeaveSeatCheckVerdictLine:
    try:
        return LeaveSeatCheckVerdictLine.model_validate_json(line)
    except ValidationError as error:
        raise HansardHandCheckError(
            f"{path}:{line_number} is not a valid verdict line: {error}"
        ) from error


def _get_packet_id_to_verdict_line(
    reader_name: str, verdicts_directory: Path, packet_ids: set[str]
) -> dict[str, LeaveSeatCheckVerdictLine]:
    verdict_lines = []
    for path in sorted(verdicts_directory.rglob(_VERDICTS_FILE_NAME)):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            verdict_lines.append(_get_verdict_line(path, line_number, line))
    packet_id_to_line_count = Counter(
        verdict_line.packet_id for verdict_line in verdict_lines
    )
    unknown_packet_ids = sorted(set(packet_id_to_line_count) - packet_ids)
    if unknown_packet_ids:
        raise HansardHandCheckError(
            f"The {reader_name} verdicts name packets that were not drawn: {unknown_packet_ids[:3]}"
        )
    packet_ids_without_one_line = sorted(
        packet_id for packet_id in packet_ids if packet_id_to_line_count[packet_id] != 1
    )
    if packet_ids_without_one_line:
        raise HansardHandCheckError(
            f"{len(packet_ids_without_one_line)} packets lack exactly one {reader_name} verdict line, the first is {packet_ids_without_one_line[0]}"
        )
    return {verdict_line.packet_id: verdict_line for verdict_line in verdict_lines}


def _get_summary_lines(
    group_to_sample_count: Counter[str],
    group_to_plant_count: Counter[str],
    group_to_sonnet_caught_count: Counter[str],
    group_to_opus_caught_count: Counter[str],
    group_to_flagged_count: Counter[str],
) -> list[str]:
    groups = sorted(set(group_to_sample_count) | set(group_to_plant_count))
    return [
        _SUMMARY_HEADER,
        *(
            f"{group}\t{group_to_sample_count[group]}\t{group_to_plant_count[group]}"
            f"\t{group_to_sonnet_caught_count[group]}\t{group_to_opus_caught_count[group]}"
            f"\t{group_to_flagged_count[group]}"
            for group in groups
        ),
        "",
    ]


def list_leave_seat_flags(
    packets_path: Path,
    sonnet_verdicts_directory: Path,
    opus_verdicts_directory: Path,
    key_path: Path,
    key_hash_path: Path,
    output_path: Path,
    summary_path: Path,
) -> None:
    key_bytes = key_path.read_bytes()
    _validate_can_open_key(key_bytes, key_hash_path.read_text(encoding="utf-8").strip())
    for path_to_write in (output_path, summary_path):
        if path_to_write.exists():
            raise HansardHandCheckError(
                f"Refusing to write: {path_to_write} already exists"
            )
    packets = [
        LeaveSeatCheckPacket.model_validate_json(line)
        for line in packets_path.read_text(encoding="utf-8").splitlines()
    ]
    packet_id_to_key_entry = {
        key_entry.packet_id: key_entry
        for key_entry in _KEY_ADAPTER.validate_json(key_bytes)
    }
    packet_ids = {packet.packet_id for packet in packets}
    if packet_ids != set(packet_id_to_key_entry):
        raise HansardHandCheckError("The packets and the key do not name the same ids")
    packet_id_to_sonnet_line = _get_packet_id_to_verdict_line(
        "Sonnet", sonnet_verdicts_directory, packet_ids
    )
    packet_id_to_opus_line = _get_packet_id_to_verdict_line(
        "Opus", opus_verdicts_directory, packet_ids
    )
    flags = []
    group_to_sample_count: Counter[str] = Counter()
    group_to_plant_count: Counter[str] = Counter()
    group_to_sonnet_caught_count: Counter[str] = Counter()
    group_to_opus_caught_count: Counter[str] = Counter()
    group_to_flagged_count: Counter[str] = Counter()
    for packet in sorted(packets, key=lambda drawn_packet: drawn_packet.packet_id):
        key_entry = packet_id_to_key_entry[packet.packet_id]
        sonnet_line = packet_id_to_sonnet_line[packet.packet_id]
        opus_line = packet_id_to_opus_line[packet.packet_id]
        if key_entry.is_plant:
            group_to_plant_count[key_entry.group] += 1
            if sonnet_line.verdict != LeaveSeatCheckVerdict.RIGHT:
                group_to_sonnet_caught_count[key_entry.group] += 1
            if opus_line.verdict != LeaveSeatCheckVerdict.RIGHT:
                group_to_opus_caught_count[key_entry.group] += 1
            continue
        group_to_sample_count[key_entry.group] += 1
        if (
            sonnet_line.verdict == LeaveSeatCheckVerdict.RIGHT
            and opus_line.verdict == LeaveSeatCheckVerdict.RIGHT
            and key_entry.group != YEAR_ORDER_BREAK_GROUP
        ):
            continue
        group_to_flagged_count[key_entry.group] += 1
        flags.append(
            LeaveSeatCheckFlag(
                packet_id=packet.packet_id,
                group=key_entry.group,
                table_name=key_entry.table_name,
                row_id=key_entry.row_id,
                source_text=packet.source_text,
                data_says=packet.data_says,
                rule=packet.rule,
                sonnet_verdict=sonnet_line.verdict,
                sonnet_note=sonnet_line.note,
                opus_verdict=opus_line.verdict,
                opus_note=opus_line.note,
            )
        )
    summary_lines = _get_summary_lines(
        group_to_sample_count,
        group_to_plant_count,
        group_to_sonnet_caught_count,
        group_to_opus_caught_count,
        group_to_flagged_count,
    )
    with output_path.open("xb") as output_file:
        output_file.write(_FLAG_ADAPTER.dump_json(flags, indent=2))
    with summary_path.open("x", encoding="utf-8") as summary_file:
        summary_file.write("\n".join(summary_lines))
    logger.info(f"Flagged {len(flags)} of {len(packets)} packets")
    for line in summary_lines:
        logger.info(line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List the leave and seat accuracy flags from both readers' verdicts, needing no database"
    )
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--sonnet-verdicts", type=Path, required=True)
    parser.add_argument("--opus-verdicts", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--key-hash", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT_PATH)
    parser.add_argument("--summary", type=Path, required=True)
    arguments = parser.parse_args()
    list_leave_seat_flags(
        arguments.packets,
        arguments.sonnet_verdicts,
        arguments.opus_verdicts,
        arguments.key,
        arguments.key_hash,
        arguments.output,
        arguments.summary,
    )
