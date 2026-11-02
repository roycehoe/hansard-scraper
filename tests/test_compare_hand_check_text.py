from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import scripts.compare_hand_check_text as compare_hand_check_text_script
from enums import HandCheckMatchStatus, SpeechKind
from schemas.hand_check_packet import HandCheckPacket, HandCheckPackets
from schemas.hand_check_snapshot import HandCheckSnapshotRow
from utils.hand_check_text import WordDifference


def _build_packet(
    packet_id: str,
    transcript: str,
    matched_source_html: str,
    match_status: HandCheckMatchStatus,
) -> HandCheckPacket:
    return HandCheckPacket(
        packet_id=packet_id,
        snapshot=HandCheckSnapshotRow(
            speech_id=1,
            report_id=2,
            hansard_report_id="r1",
            html_file_name=None,
            report_version="sprs3",
            report_type="oral-answer",
            parliament_number=15,
            sitting_date=datetime(2025, 9, 1),
            report_title="Title",
            ordinal=1,
            speaker="Mr Tan",
            speaker_id=3,
            speaker_name="Tan Wu Meng",
            person_name=None,
            kind=SpeechKind.SPEECH,
            transcript=transcript,
            next_speaker=None,
            next_transcript=None,
        ),
        official_record_url="https://example.org",
        match_status=match_status,
        matched_source_html=matched_source_html,
        context_paragraphs=[],
        after_paragraph=None,
        word_differences=[],
        gap_check=None,
        role_section=None,
        live_check_status=None,
        live_match_status=None,
    )


def test_text_the_rules_remove_leaves_no_difference() -> None:
    packet = _build_packet(
        "k1",
        "Mr Speaker, thank you.",
        "<p><b>Mr</b>&nbsp;Speaker, thank you.</p>",
        HandCheckMatchStatus.EXACT,
    )

    assert compare_hand_check_text_script.get_text_check_differences(packet) == []


def test_a_dropped_word_is_one_delete() -> None:
    packet = _build_packet(
        "k1",
        "the brown fox",
        "<p>the quick brown fox</p>",
        HandCheckMatchStatus.INEXACT,
    )

    assert compare_hand_check_text_script.get_text_check_differences(packet) == [
        WordDifference(operation="delete", source_words="quick", row_words="")
    ]


def test_glued_words_are_one_replace() -> None:
    packet = _build_packet(
        "k1",
        "thequick brown fox",
        "<p>the quick brown fox</p>",
        HandCheckMatchStatus.INEXACT,
    )

    assert compare_hand_check_text_script.get_text_check_differences(packet) == [
        WordDifference(
            operation="replace", source_words="the quick", row_words="thequick"
        )
    ]


def test_a_footnote_marker_is_a_difference() -> None:
    packet = _build_packet(
        "k1",
        "248[1] psychiatrists",
        "<p>248<sup>1</sup> psychiatrists</p>",
        HandCheckMatchStatus.INEXACT,
    )

    assert compare_hand_check_text_script.get_text_check_differences(packet) == [
        WordDifference(operation="replace", source_words="2481", row_words="248[1]")
    ]


def test_a_packet_with_no_source_has_no_differences() -> None:
    packet = _build_packet(
        "k1", "Words the report never prints.", "", HandCheckMatchStatus.NOT_FOUND
    )

    assert compare_hand_check_text_script.get_text_check_differences(packet) == []


def test_a_line_has_the_id_the_status_and_every_difference() -> None:
    packet_with_two_differences = _build_packet(
        "k1",
        "brown a fox",
        "<p>quick brown the fox</p>",
        HandCheckMatchStatus.INEXACT,
    )
    clean_packet = _build_packet(
        "k2",
        "the quick brown fox",
        "<p>the quick brown fox</p>",
        HandCheckMatchStatus.EXACT,
    )

    assert (
        compare_hand_check_text_script.get_text_check_line(packet_with_two_differences)
        == "k1\tINEXACT\t" + 'delete "quick" -> "" | replace "the" -> "a"' + "\t"
    )
    assert (
        compare_hand_check_text_script.get_text_check_line(clean_packet)
        == "k2\tEXACT\t\t"
    )


def test_a_difference_of_a_taught_kind_carries_its_kind() -> None:
    packet = _build_packet(
        "k1",
        "asked the Minister",
        "<p>(In Mandarin): asked the Minister</p>",
        HandCheckMatchStatus.INEXACT,
    )

    assert (
        compare_hand_check_text_script.get_text_check_line(packet)
        == 'k1\tINEXACT\tdelete "(In Mandarin):" -> "" (LANGUAGE_NOTE)\t'
    )


def test_a_row_with_stray_markdown_the_source_lacks_is_counted() -> None:
    stray_markdown_packet = _build_packet(
        "k1",
        "the **quick** brown __fox__",
        "<p>the quick brown fox</p>",
        HandCheckMatchStatus.EXACT,
    )
    printed_blank_packet = _build_packet(
        "k2", "Fill in __ here", "<p>Fill in __ here</p>", HandCheckMatchStatus.EXACT
    )
    not_found_packet = _build_packet(
        "k3", "the **quick** fox", "", HandCheckMatchStatus.NOT_FOUND
    )

    assert compare_hand_check_text_script.get_stray_markdown_markers(
        stray_markdown_packet
    ) == ["**", "__"]
    assert compare_hand_check_text_script.get_text_check_line(
        stray_markdown_packet
    ).endswith("\t** __")
    assert (
        compare_hand_check_text_script.get_stray_markdown_markers(printed_blank_packet)
        == []
    )
    assert (
        compare_hand_check_text_script.get_stray_markdown_markers(not_found_packet)
        == []
    )


def test_the_file_has_a_header_and_one_line_per_packet_in_order(
    tmp_path: Path,
) -> None:
    records_directory = tmp_path / "records"
    records_directory.mkdir()
    packets_path = records_directory / "packets.json"
    output_path = tmp_path / "text-check.tsv"
    packets = [
        _build_packet(
            "k1",
            "the brown fox",
            "<p>the quick brown fox</p>",
            HandCheckMatchStatus.INEXACT,
        ),
        _build_packet(
            "k2",
            "the quick brown fox",
            "<p>the quick brown fox</p>",
            HandCheckMatchStatus.EXACT,
        ),
        _build_packet(
            "k3", "Words the report never prints.", "", HandCheckMatchStatus.NOT_FOUND
        ),
    ]
    packets_path.write_text(
        HandCheckPackets(packets).model_dump_json(), encoding="utf-8"
    )

    compare_hand_check_text_script.compare_hand_check_text(packets_path, output_path)

    assert output_path.read_text(encoding="utf-8").splitlines() == [
        "packet_id\tmatch_status\tdifferences\tstray_markdown",
        'k1\tINEXACT\tdelete "quick" -> ""\t',
        "k2\tEXACT\t\t",
        "k3\tNOT_FOUND\t\t",
    ]


def test_a_malformed_packets_file_is_refused(tmp_path: Path) -> None:
    packets_path = tmp_path / "packets.json"
    output_path = tmp_path / "text-check.tsv"
    packets_path.write_text('[{"packet_id": "k1"}]', encoding="utf-8")

    with pytest.raises(ValidationError):
        compare_hand_check_text_script.compare_hand_check_text(
            packets_path, output_path
        )
    assert not output_path.exists()
