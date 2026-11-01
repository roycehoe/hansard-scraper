import argparse
from collections import Counter
from pathlib import Path

from enums import HandCheckMatchStatus
from logs import logger
from schemas.hand_check_packet import HandCheckPacket, HandCheckPackets
from utils.hand_check_text import WordDifference, get_word_differences

_HEADER_LINE = "packet_id\tmatch_status\tdifferences\tstray_markdown"
_DIFFERENCE_SEPARATOR = " | "
_STRAY_MARKDOWN_MARKERS = ("**", "__")
_STRAY_MARKDOWN_SEPARATOR = " "


def get_text_check_differences(packet: HandCheckPacket) -> list[WordDifference]:
    if packet.match_status == HandCheckMatchStatus.NOT_FOUND:
        return []
    return get_word_differences(packet.matched_source_html, packet.snapshot.transcript)


def get_stray_markdown_markers(packet: HandCheckPacket) -> list[str]:
    if packet.match_status == HandCheckMatchStatus.NOT_FOUND:
        return []
    return [
        marker
        for marker in _STRAY_MARKDOWN_MARKERS
        if marker in packet.snapshot.transcript
        and marker not in packet.matched_source_html
    ]


def get_text_check_line(packet: HandCheckPacket) -> str:
    differences_text = _DIFFERENCE_SEPARATOR.join(
        f'{difference.operation} "{difference.source_words}" -> "{difference.row_words}"'
        for difference in get_text_check_differences(packet)
    )
    stray_markdown_text = _STRAY_MARKDOWN_SEPARATOR.join(
        get_stray_markdown_markers(packet)
    )
    return f"{packet.packet_id}\t{packet.match_status.value}\t{differences_text}\t{stray_markdown_text}"


def compare_hand_check_text(packets_path: Path, output_path: Path) -> None:
    packets = HandCheckPackets.model_validate_json(
        packets_path.read_text(encoding="utf-8")
    ).root
    lines = [_HEADER_LINE, *(get_text_check_line(packet) for packet in packets)]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    match_status_to_count = Counter(packet.match_status for packet in packets)
    status_text = ", ".join(
        f"{status.value} {match_status_to_count[status]:,}"
        for status in HandCheckMatchStatus
    )
    stray_markdown_packet_count = sum(
        1 for packet in packets if get_stray_markdown_markers(packet)
    )
    logger.info(
        f"Text check of {len(packets):,} packets written: {status_text}; rows with stray ** or __: {stray_markdown_packet_count:,}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rerun the hand check's published text rules on every packet and write a TSV of packet id, match status, the word differences left and any stray ** or __ the row holds and its matched paragraph lacks, read only"
    )
    parser.add_argument(
        "packets",
        type=Path,
        help="the packet records file of the packet builder, records/packets.json in its output directory",
    )
    parser.add_argument("output", type=Path, help="write the TSV to this path")
    arguments = parser.parse_args()
    compare_hand_check_text(arguments.packets, arguments.output)
