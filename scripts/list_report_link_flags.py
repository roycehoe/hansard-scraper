import argparse
import hashlib
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from enums import ReportLinkVerdict
from exceptions import HansardReportLinkCheckError
from logs import logger
from schemas.report_link_check import (
    ReportLinkCheckFlag,
    ReportLinkCheckFlags,
    ReportLinkCheckKey,
    ReportLinkCheckPacket,
    ReportLinkCheckPackets,
    ReportLinkCheckVerdict,
)

_VERDICTS_FILE_NAME = "verdicts.jsonl"
_LISTED_PACKET_ID_COUNT = 5
_SONNET_READER_NAME = "sonnet"
_OPUS_READER_NAME = "opus"


def _get_verdict(path: Path, line_number: int, line: str) -> ReportLinkCheckVerdict:
    try:
        return ReportLinkCheckVerdict.model_validate_json(line)
    except ValidationError as error:
        raise HansardReportLinkCheckError(
            f"{path}:{line_number} is not a valid verdict line: {error}"
        ) from error


def _get_verdicts(verdicts_directory: Path) -> list[ReportLinkCheckVerdict]:
    verdicts = []
    for path in sorted(verdicts_directory.rglob(_VERDICTS_FILE_NAME)):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            verdicts.append(_get_verdict(path, line_number, line))
    return verdicts


def _get_validated_packet_id_to_verdict(
    packets: list[ReportLinkCheckPacket],
    verdicts: list[ReportLinkCheckVerdict],
    reader_name: str,
) -> dict[str, ReportLinkCheckVerdict]:
    packet_ids = [packet.packet_id for packet in packets]
    verdict_counts = Counter(verdict.packet_id for verdict in verdicts)
    unknown_packet_ids = sorted(verdict_counts.keys() - set(packet_ids))
    if unknown_packet_ids:
        raise HansardReportLinkCheckError(
            f"{reader_name} wrote verdicts for {len(unknown_packet_ids)} packets that do not exist, first {unknown_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    repeated_packet_ids = sorted(
        packet_id for packet_id, count in verdict_counts.items() if count > 1
    )
    if repeated_packet_ids:
        raise HansardReportLinkCheckError(
            f"{reader_name} wrote more than one verdict for {len(repeated_packet_ids)} packets, first {repeated_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    missing_packet_ids = [
        packet_id for packet_id in packet_ids if packet_id not in verdict_counts
    ]
    if missing_packet_ids:
        raise HansardReportLinkCheckError(
            f"{reader_name} has no verdict for {len(missing_packet_ids)} packets, first {missing_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    return {verdict.packet_id: verdict for verdict in verdicts}


def _get_validated_key(key_path: Path, key_hash_path: Path) -> ReportLinkCheckKey:
    key_bytes = key_path.read_bytes()
    key_sha256 = hashlib.sha256(key_bytes).hexdigest()
    committed_sha256 = key_hash_path.read_text(encoding="utf-8").strip()
    if key_sha256 != committed_sha256:
        raise HansardReportLinkCheckError(
            f"The plant key hashes to {key_sha256}, not the committed {committed_sha256}"
        )
    return ReportLinkCheckKey.model_validate_json(key_bytes)


def _log_recall(
    key: ReportLinkCheckKey,
    reader_name: str,
    packet_id_to_verdict: dict[str, ReportLinkCheckVerdict],
) -> None:
    missed_packet_ids = [
        plant.packet_id
        for plant in key.plants
        if packet_id_to_verdict[plant.packet_id].verdict == ReportLinkVerdict.RIGHT
    ]
    logger.info(
        f"{reader_name}: caught {len(key.plants) - len(missed_packet_ids)} of {len(key.plants)} plants, missed {missed_packet_ids}"
    )


def _build_flag(
    packet: ReportLinkCheckPacket,
    reader_name_to_packet_id_to_verdict: dict[str, dict[str, ReportLinkCheckVerdict]],
) -> ReportLinkCheckFlag:
    return ReportLinkCheckFlag(
        packet_id=packet.packet_id,
        group=packet.group,
        rule=packet.rule,
        link_type=packet.link_type,
        source_report_id=packet.source_report_id,
        target_report_id=packet.target_report_id,
        printed_citation=packet.printed_citation,
        paragraph=packet.paragraph,
        what_the_data_says=f"The link points to {packet.target_report.title}, {packet.target_report.sitting_date}.",
        reader_notes=[
            f"{reader_name}: {packet_id_to_verdict[packet.packet_id].verdict}: {packet_id_to_verdict[packet.packet_id].note}"
            for reader_name, packet_id_to_verdict in reader_name_to_packet_id_to_verdict.items()
            if packet_id_to_verdict[packet.packet_id].verdict != ReportLinkVerdict.RIGHT
        ],
    )


def list_report_link_flags(
    packets_path: Path,
    key_path: Path,
    key_hash_path: Path,
    sonnet_verdicts_directory: Path,
    opus_verdicts_directory: Path,
    output_path: Path,
) -> None:
    packets = ReportLinkCheckPackets.model_validate_json(
        packets_path.read_text(encoding="utf-8")
    ).root
    key = _get_validated_key(key_path, key_hash_path)
    reader_name_to_packet_id_to_verdict = {
        _SONNET_READER_NAME: _get_validated_packet_id_to_verdict(
            packets, _get_verdicts(sonnet_verdicts_directory), _SONNET_READER_NAME
        ),
        _OPUS_READER_NAME: _get_validated_packet_id_to_verdict(
            packets, _get_verdicts(opus_verdicts_directory), _OPUS_READER_NAME
        ),
    }
    plant_packet_ids = {plant.packet_id for plant in key.plants}
    unknown_plant_packet_ids = sorted(
        plant_packet_ids - {packet.packet_id for packet in packets}
    )
    if unknown_plant_packet_ids:
        raise HansardReportLinkCheckError(
            f"The plant key names {len(unknown_plant_packet_ids)} packets that do not exist, first {unknown_plant_packet_ids[:_LISTED_PACKET_ID_COUNT]}"
        )
    for (
        reader_name,
        packet_id_to_verdict,
    ) in reader_name_to_packet_id_to_verdict.items():
        _log_recall(key, reader_name, packet_id_to_verdict)
        logger.info(
            f"{reader_name} verdicts: {dict(Counter(verdict.verdict for verdict in packet_id_to_verdict.values()))}"
        )
    flags = [
        _build_flag(packet, reader_name_to_packet_id_to_verdict)
        for packet in packets
        if packet.packet_id not in plant_packet_ids
        and any(
            packet_id_to_verdict[packet.packet_id].verdict != ReportLinkVerdict.RIGHT
            for packet_id_to_verdict in reader_name_to_packet_id_to_verdict.values()
        )
    ]
    with output_path.open("x", encoding="utf-8") as output_file:
        output_file.write(ReportLinkCheckFlags(flags).model_dump_json(indent=2))
    logger.info(
        f"Flags by group: {dict(Counter(flag.group for flag in flags))}, {len(flags):,} in all"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="List the report link check's flags from the packets and the readers' verdicts, read only; score each reader's catches of the planted errors with the sealed key"
    )
    parser.add_argument(
        "--packets",
        type=Path,
        required=True,
        help="records/packets.json in the check's output directory",
    )
    parser.add_argument(
        "--key",
        type=Path,
        required=True,
        help="key/plant-key.json in the check's output directory",
    )
    parser.add_argument(
        "--key-hash",
        type=Path,
        required=True,
        help="key/plant-key.sha256, the hash the key must match",
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
        "--output",
        type=Path,
        required=True,
        help="write the flag list (JSON) to this path; the file must not exist yet",
    )
    arguments = parser.parse_args()
    list_report_link_flags(
        arguments.packets,
        arguments.key,
        arguments.key_hash,
        arguments.sonnet_verdicts,
        arguments.opus_verdicts,
        arguments.output,
    )
