import argparse
import hashlib
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from enums import LawLinkCheckRule, LawLinkVerdict
from exceptions import HansardLawLinkCheckError
from logs import logger
from schemas.law_link_check_flag import LawLinkCheckFlag, LawLinkCheckFlags
from schemas.law_link_check_packet import LawLinkCheckPacket, LawLinkCheckPackets
from schemas.law_link_check_plant_key import LawLinkCheckPlant, LawLinkCheckPlantKey
from schemas.law_link_check_verdict import LawLinkCheckVerdict

_VERDICTS_FILE_NAME = "verdicts.jsonl"
_LISTED_PACKET_ID_COUNT = 5
_ONE_SIDED_ALPHA = 0.05
_SONNET_READER_NAME = "Sonnet"
_OPUS_READER_NAME = "Opus"


def _get_verdict(path: Path, line_number: int, line: str) -> LawLinkCheckVerdict:
    try:
        return LawLinkCheckVerdict.model_validate_json(line)
    except ValidationError as error:
        raise HansardLawLinkCheckError(
            f"{path}:{line_number} is not a valid verdict line: {error}"
        ) from error


def get_verdicts(verdicts_directory: Path) -> list[LawLinkCheckVerdict]:
    verdicts = []
    for path in sorted(verdicts_directory.rglob(_VERDICTS_FILE_NAME)):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            verdicts.append(_get_verdict(path, line_number, line))
    return verdicts


def get_packet_id_to_verdict(
    packets: list[LawLinkCheckPacket],
    verdicts: list[LawLinkCheckVerdict],
    reader_name: str,
) -> dict[str, LawLinkCheckVerdict]:
    packet_ids = [packet.packet_id for packet in packets]
    verdict_counts = Counter(verdict.packet_id for verdict in verdicts)
    unknown_packet_ids = sorted(verdict_counts.keys() - set(packet_ids))
    if unknown_packet_ids:
        raise HansardLawLinkCheckError(
            f"{reader_name} wrote verdicts for {len(unknown_packet_ids)} packets that do not exist, first {unknown_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    repeated_packet_ids = sorted(
        packet_id for packet_id, count in verdict_counts.items() if count > 1
    )
    if repeated_packet_ids:
        raise HansardLawLinkCheckError(
            f"{reader_name} wrote more than one verdict for {len(repeated_packet_ids)} packets, first {repeated_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    missing_packet_ids = [
        packet_id for packet_id in packet_ids if packet_id not in verdict_counts
    ]
    if missing_packet_ids:
        raise HansardLawLinkCheckError(
            f"{reader_name} has no verdict for {len(missing_packet_ids)} packets, first {missing_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    return {verdict.packet_id: verdict for verdict in verdicts}


def validate_can_open_plant_key(key_bytes: bytes, committed_sha256: str) -> None:
    key_sha256 = hashlib.sha256(key_bytes).hexdigest()
    if key_sha256 != committed_sha256:
        raise HansardLawLinkCheckError(
            f"The plant key hashes to {key_sha256}, not the committed {committed_sha256}"
        )


def get_plants(key_path: Path, hash_path: Path) -> list[LawLinkCheckPlant]:
    key_bytes = key_path.read_bytes()
    validate_can_open_plant_key(
        key_bytes, hash_path.read_text(encoding="utf-8").strip()
    )
    try:
        return LawLinkCheckPlantKey.model_validate_json(key_bytes).plants
    except ValidationError as error:
        raise HansardLawLinkCheckError(
            f"The plant key does not match its schema: {error}"
        ) from error


def _is_verdict_not_right(verdict: LawLinkCheckVerdict) -> bool:
    return verdict.verdict != LawLinkVerdict.RIGHT


def get_flags(
    packets: list[LawLinkCheckPacket],
    packet_id_to_sonnet_verdict: dict[str, LawLinkCheckVerdict],
    packet_id_to_opus_verdict: dict[str, LawLinkCheckVerdict],
) -> list[LawLinkCheckFlag]:
    flags = []
    for packet in packets:
        sonnet_verdict = packet_id_to_sonnet_verdict[packet.packet_id]
        opus_verdict = packet_id_to_opus_verdict[packet.packet_id]
        if not (
            _is_verdict_not_right(sonnet_verdict) or _is_verdict_not_right(opus_verdict)
        ):
            continue
        flags.append(
            LawLinkCheckFlag(
                packet_id=packet.packet_id,
                rule=packet.rule,
                group=packet.group,
                row_id=packet.row_id,
                source_text=packet.source_text,
                data_says=packet.data_says,
                rule_text=packet.rule_text,
                sonnet_verdict=sonnet_verdict,
                opus_verdict=opus_verdict,
            )
        )
    return sorted(flags, key=lambda flag: (flag.rule.value, flag.row_id))


def get_missed_plants(
    plants: list[LawLinkCheckPlant],
    packet_id_to_verdict: dict[str, LawLinkCheckVerdict],
) -> list[LawLinkCheckPlant]:
    missed_plants = []
    for plant in plants:
        try:
            verdict = packet_id_to_verdict[plant.packet_id]
        except KeyError as error:
            raise HansardLawLinkCheckError(
                f"Planted packet id {plant.packet_id} has no packet"
            ) from error
        if verdict.verdict == LawLinkVerdict.RIGHT:
            missed_plants.append(plant)
    return missed_plants


def get_recall_lines(
    reader_name: str,
    plants: list[LawLinkCheckPlant],
    missed_plants: list[LawLinkCheckPlant],
) -> list[str]:
    rule_to_plant_count = Counter(plant.rule for plant in plants)
    rule_to_missed_count = Counter(plant.rule for plant in missed_plants)
    lines = [
        f"{reader_name} caught {len(plants) - len(missed_plants)} of {len(plants)} planted errors"
    ]
    for rule in LawLinkCheckRule:
        caught_count = rule_to_plant_count[rule] - rule_to_missed_count[rule]
        lines.append(
            f"  {rule.value}: caught {caught_count} of {rule_to_plant_count[rule]}"
        )
    lines.extend(
        f"  missed {plant.rule.value}, packet {plant.packet_id}"
        for plant in missed_plants
    )
    if not missed_plants:
        lines.append(
            f"  recall at least {_ONE_SIDED_ALPHA ** (1 / len(plants)):.1%} (one-sided exact 95%)"
        )
    return lines


def get_summary_lines(
    sampled_packets: list[LawLinkCheckPacket],
    flags: list[LawLinkCheckFlag],
) -> list[str]:
    rule_to_packet_count = Counter(packet.rule for packet in sampled_packets)
    rule_to_flag_count = Counter(flag.rule for flag in flags)
    return [
        "Law link check flags",
        f"Sampled rows: {len(sampled_packets)}",
        f"Flags: {len(flags)}",
        "Flags by rule:",
        *(
            f"  {rule.value}: {rule_to_flag_count[rule]} of {rule_to_packet_count[rule]}"
            for rule in LawLinkCheckRule
        ),
        "Flags by reader (a row can be flagged by both):",
        f"  Sonnet: {sum(1 for flag in flags if _is_verdict_not_right(flag.sonnet_verdict))}",
        f"  Opus: {sum(1 for flag in flags if _is_verdict_not_right(flag.opus_verdict))}",
    ]


def list_law_link_flags(
    packets_path: Path,
    sonnet_verdicts_path: Path,
    opus_verdicts_path: Path,
    key_path: Path,
    hash_path: Path,
    flags_path: Path,
    summary_path: Path,
) -> None:
    packets = LawLinkCheckPackets.model_validate_json(
        packets_path.read_text(encoding="utf-8")
    ).root
    packet_id_to_sonnet_verdict = get_packet_id_to_verdict(
        packets, get_verdicts(sonnet_verdicts_path), _SONNET_READER_NAME
    )
    packet_id_to_opus_verdict = get_packet_id_to_verdict(
        packets, get_verdicts(opus_verdicts_path), _OPUS_READER_NAME
    )
    plants = get_plants(key_path, hash_path)
    if not plants:
        raise HansardLawLinkCheckError("The plant key holds no plant to score")
    plant_packet_ids = frozenset(plant.packet_id for plant in plants)
    sampled_packets = [
        packet for packet in packets if packet.packet_id not in plant_packet_ids
    ]
    flags = get_flags(
        sampled_packets, packet_id_to_sonnet_verdict, packet_id_to_opus_verdict
    )
    lines = get_summary_lines(sampled_packets, flags)
    missed_reader_names = []
    for reader_name, packet_id_to_verdict in (
        (_SONNET_READER_NAME, packet_id_to_sonnet_verdict),
        (_OPUS_READER_NAME, packet_id_to_opus_verdict),
    ):
        missed_plants = get_missed_plants(plants, packet_id_to_verdict)
        lines.extend(get_recall_lines(reader_name, plants, missed_plants))
        if missed_plants:
            missed_reader_names.append(reader_name)
    lines.append(
        f"Readers that missed a plant: {', '.join(missed_reader_names) or 'none'}"
    )
    with flags_path.open("x", encoding="utf-8") as flags_file:
        flags_file.write(LawLinkCheckFlags(flags).model_dump_json(indent=1))
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        logger.info(line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List the law link check's flags from the packets and both readers' verdicts, read only, and score each reader's catches of the planted errors with the sealed key"
    )
    parser.add_argument(
        "packets",
        type=Path,
        help="the packet records file of the draw, records/packets.json in its output directory",
    )
    parser.add_argument(
        "--sonnet-verdicts",
        type=Path,
        required=True,
        help="the Sonnet verdicts directory: every verdicts.jsonl under it is read",
    )
    parser.add_argument(
        "--opus-verdicts",
        type=Path,
        required=True,
        help="the Opus verdicts directory: every verdicts.jsonl under it is read",
    )
    parser.add_argument(
        "--key", type=Path, required=True, help="the sealed plant key of the draw"
    )
    parser.add_argument(
        "--key-hash",
        type=Path,
        required=True,
        help="the committed file holding the key's SHA-256",
    )
    parser.add_argument(
        "--flags",
        type=Path,
        required=True,
        help="write the flag list (JSON) to this path, such as RUN/flags/laws.json; the file must not exist yet",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        required=True,
        help="write the summary text to this path",
    )
    arguments = parser.parse_args()
    list_law_link_flags(
        arguments.packets,
        arguments.sonnet_verdicts,
        arguments.opus_verdicts,
        arguments.key,
        arguments.key_hash,
        arguments.flags,
        arguments.summary,
    )
