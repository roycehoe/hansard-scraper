import argparse
import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from enums import (
    HandCheckFlagReason,
    HandCheckLiveCheckStatus,
    HandCheckMatchStatus,
    HandCheckPlantKind,
    HandCheckSpeakerVerdict,
)
from exceptions import HansardHandCheckError
from logs import logger
from schemas.fresh_parse_plan import HeldReports
from schemas.hand_check_flag import HandCheckFlag, HandCheckFlags
from schemas.hand_check_packet import HandCheckPacket, HandCheckPackets
from schemas.hand_check_plant_key import HandCheckPlant, HandCheckPlantKey
from schemas.hand_check_verdict import HandCheckVerdict

_VERDICTS_FILE_NAME = "verdicts.jsonl"
_LISTED_PACKET_ID_COUNT = 5
_ONE_SIDED_ALPHA = 0.05
_FIRST_RUN_NUMBER = 1
_MAX_RUN_NUMBER = 2


@dataclass(frozen=True)
class PlantKeyPaths:
    key_path: Path
    hash_path: Path


@dataclass(frozen=True)
class HandCheckReader:
    name: str
    is_shown_word_differences: bool


SONNET_READER = HandCheckReader(name="Sonnet", is_shown_word_differences=True)
OPUS_READER = HandCheckReader(name="Opus", is_shown_word_differences=False)


def _get_verdict(path: Path, line_number: int, line: str) -> HandCheckVerdict:
    try:
        return HandCheckVerdict.model_validate_json(line)
    except ValidationError as error:
        raise HansardHandCheckError(
            f"{path}:{line_number} is not a valid verdict line: {error}"
        ) from error


def get_verdicts(verdicts_directory: Path) -> list[HandCheckVerdict]:
    verdicts = []
    for path in sorted(verdicts_directory.rglob(_VERDICTS_FILE_NAME)):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            verdicts.append(_get_verdict(path, line_number, line))
    return verdicts


def get_expected_class_count(packet: HandCheckPacket, reader: HandCheckReader) -> int:
    if (
        reader.is_shown_word_differences
        and packet.match_status == HandCheckMatchStatus.INEXACT
    ):
        return len(packet.word_differences)
    return 0


def get_packet_id_to_verdict(
    packets: list[HandCheckPacket],
    verdicts: list[HandCheckVerdict],
    reader: HandCheckReader,
) -> dict[str, HandCheckVerdict]:
    packet_ids = [packet.packet_id for packet in packets]
    verdict_counts = Counter(verdict.packet_id for verdict in verdicts)
    unknown_packet_ids = sorted(verdict_counts.keys() - set(packet_ids))
    if unknown_packet_ids:
        raise HansardHandCheckError(
            f"{reader.name} wrote verdicts for {len(unknown_packet_ids)} packets that do not exist, first {unknown_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    repeated_packet_ids = sorted(
        packet_id for packet_id, count in verdict_counts.items() if count > 1
    )
    if repeated_packet_ids:
        raise HansardHandCheckError(
            f"{reader.name} wrote more than one verdict for {len(repeated_packet_ids)} packets, first {repeated_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    missing_packet_ids = [
        packet_id for packet_id in packet_ids if packet_id not in verdict_counts
    ]
    if missing_packet_ids:
        raise HansardHandCheckError(
            f"{reader.name} has no verdict for {len(missing_packet_ids)} packets, first {missing_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    packet_id_to_verdict = {verdict.packet_id: verdict for verdict in verdicts}
    miscounted_packet_ids = [
        packet.packet_id
        for packet in packets
        if len(packet_id_to_verdict[packet.packet_id].difference_classes)
        != get_expected_class_count(packet, reader)
    ]
    if miscounted_packet_ids:
        raise HansardHandCheckError(
            f"{reader.name} gave the wrong number of difference classes for {len(miscounted_packet_ids)} packets, first {miscounted_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    return packet_id_to_verdict


def validate_can_open_plant_key(key_bytes: bytes, committed_sha256: str) -> None:
    key_sha256 = hashlib.sha256(key_bytes).hexdigest()
    if key_sha256 != committed_sha256:
        raise HansardHandCheckError(
            f"The plant key hashes to {key_sha256}, not the committed {committed_sha256}"
        )


def _get_plants(plant_key_paths: PlantKeyPaths) -> list[HandCheckPlant]:
    key_bytes = plant_key_paths.key_path.read_bytes()
    validate_can_open_plant_key(
        key_bytes, plant_key_paths.hash_path.read_text(encoding="utf-8").strip()
    )
    try:
        return HandCheckPlantKey.model_validate_json(key_bytes).plants
    except ValidationError as error:
        raise HansardHandCheckError(
            f"The plant key does not match its schema: {error}"
        ) from error


def get_missed_plants(
    plants: list[HandCheckPlant], speech_id_to_verdict: dict[int, HandCheckVerdict]
) -> list[HandCheckPlant]:
    missed_plants = []
    for plant in plants:
        try:
            verdict = speech_id_to_verdict[plant.speech_id]
        except KeyError as error:
            raise HansardHandCheckError(
                f"Planted speech id {plant.speech_id} has no packet"
            ) from error
        if verdict.speaker_verdict == HandCheckSpeakerVerdict.RIGHT:
            missed_plants.append(plant)
    return missed_plants


def get_recall_lines(
    reader_name: str, plants: list[HandCheckPlant], missed_plants: list[HandCheckPlant]
) -> list[str]:
    plant_kind_to_count = Counter(plant.kind for plant in plants)
    missed_kind_to_count = Counter(plant.kind for plant in missed_plants)
    lines = [
        f"{reader_name} caught {len(plants) - len(missed_plants)} of {len(plants)} planted errors"
    ]
    for kind in HandCheckPlantKind:
        caught_count = plant_kind_to_count[kind] - missed_kind_to_count[kind]
        lines.append(
            f"  {kind.value}: caught {caught_count} of {plant_kind_to_count[kind]}"
        )
    lines.extend(
        f"  missed {plant.kind.value}, speech id {plant.speech_id}"
        for plant in missed_plants
    )
    if not missed_plants:
        lines.append(
            f"  recall at least {_ONE_SIDED_ALPHA ** (1 / len(plants)):.1%} (one-sided exact 95%)"
        )
    return lines


def get_missed_reader_line(missed_reader_names: list[str]) -> str:
    return f"Readers that missed a plant: {', '.join(missed_reader_names) or 'none'}"


def _is_speaker_verdict_not_right(verdict: Optional[HandCheckVerdict]) -> bool:
    return (
        verdict is not None and verdict.speaker_verdict != HandCheckSpeakerVerdict.RIGHT
    )


def get_flag_reasons(
    packet: HandCheckPacket,
    sonnet_verdict: Optional[HandCheckVerdict],
    opus_verdict: Optional[HandCheckVerdict],
) -> list[HandCheckFlagReason]:
    reasons = []
    if any(
        _is_speaker_verdict_not_right(verdict)
        for verdict in (sonnet_verdict, opus_verdict)
    ):
        reasons.append(HandCheckFlagReason.SPEAKER_VERDICT)
    if packet.word_differences:
        reasons.append(HandCheckFlagReason.TEXT_DIFFERENCE)
    if packet.match_status != HandCheckMatchStatus.EXACT:
        reasons.append(HandCheckFlagReason.MATCH_STATUS)
    if packet.live_check_status == HandCheckLiveCheckStatus.DIFFERS:
        reasons.append(HandCheckFlagReason.LIVE_TEXT_DIFFERS)
    return reasons


def get_flags(
    packets: list[HandCheckPacket],
    packet_id_to_sonnet_verdict: Optional[dict[str, HandCheckVerdict]],
    packet_id_to_opus_verdict: Optional[dict[str, HandCheckVerdict]],
    run_number: int,
) -> list[HandCheckFlag]:
    flags = []
    for packet in packets:
        sonnet_verdict = (
            None
            if packet_id_to_sonnet_verdict is None
            else packet_id_to_sonnet_verdict[packet.packet_id]
        )
        opus_verdict = (
            None
            if packet_id_to_opus_verdict is None
            else packet_id_to_opus_verdict[packet.packet_id]
        )
        reasons = get_flag_reasons(packet, sonnet_verdict, opus_verdict)
        if not reasons:
            continue
        flags.append(
            HandCheckFlag(
                packet_id=packet.packet_id,
                speech_id=packet.snapshot.speech_id,
                run_number=run_number,
                reasons=reasons,
                sonnet_speaker_verdict=sonnet_verdict,
                opus_speaker_verdict=opus_verdict,
                word_differences=packet.word_differences,
                match_status=packet.match_status,
            )
        )
    return flags


def _get_latest_verdict(
    verdict: Optional[HandCheckVerdict], earlier_verdict: Optional[HandCheckVerdict]
) -> Optional[HandCheckVerdict]:
    return earlier_verdict if verdict is None else verdict


def _get_merged_flag(earlier_flag: HandCheckFlag, flag: HandCheckFlag) -> HandCheckFlag:
    return HandCheckFlag(
        packet_id=flag.packet_id,
        speech_id=flag.speech_id,
        run_number=flag.run_number,
        reasons=[
            reason
            for reason in HandCheckFlagReason
            if reason in earlier_flag.reasons or reason in flag.reasons
        ],
        sonnet_speaker_verdict=_get_latest_verdict(
            flag.sonnet_speaker_verdict, earlier_flag.sonnet_speaker_verdict
        ),
        opus_speaker_verdict=_get_latest_verdict(
            flag.opus_speaker_verdict, earlier_flag.opus_speaker_verdict
        ),
        word_differences=flag.word_differences,
        match_status=flag.match_status,
    )


def get_union_of_flags(
    earlier_flags: list[HandCheckFlag], flags: list[HandCheckFlag]
) -> list[HandCheckFlag]:
    speech_id_to_flag = {flag.speech_id: flag for flag in earlier_flags}
    for flag in flags:
        earlier_flag = speech_id_to_flag.get(flag.speech_id)
        speech_id_to_flag[flag.speech_id] = (
            flag if earlier_flag is None else _get_merged_flag(earlier_flag, flag)
        )
    return [speech_id_to_flag[speech_id] for speech_id in sorted(speech_id_to_flag)]


def get_summary_lines(
    run_number: int,
    sampled_packets: list[HandCheckPacket],
    flags: list[HandCheckFlag],
    kept_flag_count: int,
    held_report_ids: Optional[frozenset[int]],
) -> list[str]:
    reason_to_count = Counter(reason for flag in flags for reason in flag.reasons)
    match_status_to_count = Counter(packet.match_status for packet in sampled_packets)
    gap_checks = [
        packet.gap_check for packet in sampled_packets if packet.gap_check is not None
    ]
    gap_count = sum(1 for gap_check in gap_checks if not gap_check.is_next_row)
    role_sections = [
        packet.role_section
        for packet in sampled_packets
        if packet.role_section is not None
    ]
    chair_mark_count = sum(
        1
        for role_section in role_sections
        if role_section.is_chair_label and role_section.chair_marks
    )
    table_entry_count = sum(
        1
        for role_section in role_sections
        if not role_section.is_chair_label and role_section.office_holders
    )
    lines = [
        f"Hand check flags, run {run_number}",
        f"Sampled rows: {len(sampled_packets)}",
        f"Flags: {len(flags)}, of which {kept_flag_count} kept from an earlier run",
        "Flags by reason (one flag can have several):",
        *(
            f"  {reason.value}: {reason_to_count[reason]}"
            for reason in HandCheckFlagReason
        ),
        "Flags whose speaker verdict is not right, by reader (a missing verdict counts as right):",
        f"  Sonnet: {sum(1 for flag in flags if _is_speaker_verdict_not_right(flag.sonnet_speaker_verdict))}",
        f"  Opus: {sum(1 for flag in flags if _is_speaker_verdict_not_right(flag.opus_speaker_verdict))}",
        "Match status:",
        *(
            f"  {status.value}: {match_status_to_count[status]}"
            for status in HandCheckMatchStatus
        ),
        f"Gap check: {gap_count} of {len(gap_checks)} checked rows are not followed by the next source paragraph",
        f"Role credits (packet side): {len(role_sections)} rows",
        f"  chair label with a chair mark: {chair_mark_count}",
        f"  office label with a table entry: {table_entry_count}",
        f"  no chair mark or table entry: {len(role_sections) - chair_mark_count - table_entry_count}",
    ]
    if held_report_ids is not None:
        held_row_count = sum(
            1
            for packet in sampled_packets
            if packet.snapshot.report_id in held_report_ids
        )
        lines.append(f"Rows in held reports: {held_row_count}")
    return lines


def _validate_can_write_flags(
    sonnet_verdicts_path: Optional[Path],
    opus_verdicts_path: Optional[Path],
    run_number: int,
    earlier_flags_path: Optional[Path],
) -> None:
    if run_number > _FIRST_RUN_NUMBER and earlier_flags_path is None:
        raise HansardHandCheckError(
            f"Run {run_number} needs the flag list of the run before (--earlier-flags)"
        )
    if run_number > _MAX_RUN_NUMBER:
        raise HansardHandCheckError(
            f"Run {run_number} is refused: the plan allows one rerun, so run {_MAX_RUN_NUMBER} is the last (P4)"
        )
    if run_number == _FIRST_RUN_NUMBER and sonnet_verdicts_path is None:
        raise HansardHandCheckError(
            "Run 1 needs both readers' verdicts (--sonnet-verdicts and --opus-verdicts)"
        )
    if run_number == _FIRST_RUN_NUMBER and opus_verdicts_path is None:
        raise HansardHandCheckError(
            "Run 1 needs both readers' verdicts (--sonnet-verdicts and --opus-verdicts)"
        )
    if (
        run_number > _FIRST_RUN_NUMBER
        and sonnet_verdicts_path is None
        and opus_verdicts_path is None
    ):
        raise HansardHandCheckError(
            f"Run {run_number} needs at least one reader's verdicts (--sonnet-verdicts or --opus-verdicts)"
        )


def list_hand_check_flags(
    packets_path: Path,
    sonnet_verdicts_path: Optional[Path],
    opus_verdicts_path: Optional[Path],
    flags_path: Path,
    summary_path: Path,
    run_number: int,
    plant_key_paths: Optional[PlantKeyPaths],
    earlier_flags_path: Optional[Path],
    held_reports_path: Optional[Path],
) -> None:
    _validate_can_write_flags(
        sonnet_verdicts_path, opus_verdicts_path, run_number, earlier_flags_path
    )
    packets = HandCheckPackets.model_validate_json(
        packets_path.read_text(encoding="utf-8")
    ).root
    packet_id_to_sonnet_verdict = (
        None
        if sonnet_verdicts_path is None
        else get_packet_id_to_verdict(
            packets, get_verdicts(sonnet_verdicts_path), SONNET_READER
        )
    )
    packet_id_to_opus_verdict = (
        None
        if opus_verdicts_path is None
        else get_packet_id_to_verdict(
            packets, get_verdicts(opus_verdicts_path), OPUS_READER
        )
    )
    plants = [] if plant_key_paths is None else _get_plants(plant_key_paths)
    plant_speech_ids = frozenset(plant.speech_id for plant in plants)
    sampled_packets = [
        packet
        for packet in packets
        if packet.snapshot.speech_id not in plant_speech_ids
    ]
    flags = get_flags(
        sampled_packets,
        packet_id_to_sonnet_verdict,
        packet_id_to_opus_verdict,
        run_number,
    )
    earlier_flags = (
        []
        if earlier_flags_path is None
        else HandCheckFlags.model_validate_json(
            earlier_flags_path.read_text(encoding="utf-8")
        ).root
    )
    listed_flags = get_union_of_flags(earlier_flags, flags)
    held_report_ids = (
        None
        if held_reports_path is None
        else frozenset(
            held_report.report_id
            for held_report in HeldReports.model_validate_json(
                held_reports_path.read_text(encoding="utf-8")
            ).root
        )
    )
    lines = get_summary_lines(
        run_number,
        sampled_packets,
        listed_flags,
        len(listed_flags) - len(flags),
        held_report_ids,
    )
    if plant_key_paths is not None:
        missed_reader_names = []
        for reader, packet_id_to_verdict in (
            (SONNET_READER, packet_id_to_sonnet_verdict),
            (OPUS_READER, packet_id_to_opus_verdict),
        ):
            if packet_id_to_verdict is None:
                continue
            speech_id_to_verdict = {
                packet.snapshot.speech_id: packet_id_to_verdict[packet.packet_id]
                for packet in packets
            }
            missed_plants = get_missed_plants(plants, speech_id_to_verdict)
            lines.extend(get_recall_lines(reader.name, plants, missed_plants))
            if missed_plants:
                missed_reader_names.append(reader.name)
        lines.append(get_missed_reader_line(missed_reader_names))
    with flags_path.open("x", encoding="utf-8") as flags_file:
        flags_file.write(HandCheckFlags(listed_flags).model_dump_json(indent=1))
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        logger.info(line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List the hand check's flags from the packets and the readers' verdicts, read only; with the sealed key, score each given reader's catches of the planted errors"
    )
    parser.add_argument(
        "packets",
        type=Path,
        help="the packet records file of the packet builder, records/packets.json in its output directory",
    )
    parser.add_argument(
        "--sonnet-verdicts",
        type=Path,
        help="the Sonnet verdicts directory: every verdicts.jsonl under it is read; leave out in a rerun that does not rerun Sonnet",
    )
    parser.add_argument(
        "--opus-verdicts",
        type=Path,
        help="the Opus verdicts directory: every verdicts.jsonl under it is read; leave out in a rerun that does not rerun Opus",
    )
    parser.add_argument(
        "--flags",
        type=Path,
        required=True,
        help="write the flag list (JSON) to this path; the file must not exist yet",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        required=True,
        help="write the summary text to this path",
    )
    parser.add_argument(
        "--run-number",
        type=int,
        default=1,
        help="1 for the first run, which needs both readers; 2 for the rerun of plan P4, which needs at least one",
    )
    parser.add_argument(
        "--key",
        type=Path,
        help="the sealed plant key; leave out for the pilot, which has no plants",
    )
    parser.add_argument(
        "--key-hash",
        type=Path,
        help="the committed file holding the key's SHA-256; required with --key",
    )
    parser.add_argument(
        "--earlier-flags",
        type=Path,
        help="the flag list of the run before; required from run 2; every row it flags stays flagged",
    )
    parser.add_argument(
        "--held",
        type=Path,
        help="a held-reports file, as apply_fresh_parse reads: counts the sampled rows in those reports",
    )
    arguments = parser.parse_args()
    if (arguments.key is None) != (arguments.key_hash is None):
        parser.error("--key and --key-hash go together")
    plant_key_paths = (
        None
        if arguments.key is None
        else PlantKeyPaths(arguments.key, arguments.key_hash)
    )
    list_hand_check_flags(
        arguments.packets,
        arguments.sonnet_verdicts,
        arguments.opus_verdicts,
        arguments.flags,
        arguments.summary,
        arguments.run_number,
        plant_key_paths,
        arguments.earlier_flags,
        arguments.held,
    )
