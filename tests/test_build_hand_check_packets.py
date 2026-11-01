import random
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pytest

import scripts.build_hand_check_packets as build_hand_check_packets_script
from database.report import Report
from enums import (
    HandCheckAnswerStatus,
    HandCheckFormOfAddress,
    HandCheckLiveCheckStatus,
    HandCheckMatchStatus,
    ReportType,
    ReportVersion,
    SpeechKind,
)
from exceptions import HansardHandCheckError
from schemas.hand_check_office_holder import HandCheckOfficeHolder
from schemas.hand_check_packet import (
    HandCheckPacket,
    HandCheckPackets,
    HandCheckWordDifference,
)
from schemas.hand_check_snapshot import HandCheckSnapshotRow
from schemas.hansard_topic_response import (
    HansardTopicResponse,
    HansardTopicResultHtml,
)
from tests.hand_check_source_html import SPRS2_COMMITTEE_HTML, SPRS3_ORAL_ANSWER_HTML

_TAG_LINE = "MPs Speaking: Dr Tony Tan Keng Yam (Minister for Defence); Mr Chew Heng Ching (Mr Deputy Speaker);"
_THEREUPON_LINE = "Thereupon, Mr Deputy Speaker left the Chair of the Committee and took the Chair of the House."
_JOINED_ROW = (
    "Therefore, it is more prudent to have our current rules as the default position."
    " However, financial institutions may approve property loan applications where the"
    " borrowers' TDSR exceed 60% in exceptional cases. Such exceptions must be approved by"
    " the financial institutions' credit committees, in line with the policies set by their"
    " board of directors."
)
_NEXT_ROW = "Madam, a supplementary question for the Minister."
_MINISTER_LABEL = "The Minister for Education (Higher Education and Skills) and Second Minister for Defence (Mr Ong Ye Kung) (for the Prime Minister)"
_OFFICE_HTML = "<p><strong>The Prime Minister</strong>: Thank you, Mr Speaker.</p><p>Next paragraph here.</p>"
_TWO_DEPUTIES_HTML = "<p>[Mr Deputy Speaker in the Chair]</p><p><b>Mr Deputy Speaker:</b> Order.</p><p><b>The Chairman:</b> Yes.</p>"
_SPEECH_ID = 9_876_543
_REPORT_ID = 8_765_432
_SPEAKER_ID = 7_654_321
_HANSARD_REPORT_ID = "00123456-ZZ.00123457-ZZ_1#"
_OFFICIAL_RECORD_URL = (
    "https://sprs.parl.gov.sg/search/#/sprs3topic?reportid=00123456-ZZ.00123457-ZZ_1"
)
_PACKET_ID = "abc123def456"
_INEXACT_ROW = _JOINED_ROW.replace("as the default position", "as default position")
_SUPERSCRIPT_HTML = "<p><b>Mr A:</b> The total for the year was 248<sup>1</sup> people in all of the country.</p>"
_SUPERSCRIPT_ROW = "The total for the year was 248[1] people in all of the country."
_LIVE_CHECK_REPORT_COUNT = 50
_JOINED_ROW_CONTEXT_PARAGRAPH_COUNT = 3
_PACKET_ID_COUNT = 1_030
_PACKET_ID_LENGTH = 12
_HEXADECIMAL_BASE = 16
_BATCH_SIZES = [50, 50, 25]
_LONG_PACKET_LENGTH = 30_000
_HALF_LIMIT_PACKET_LENGTH = 40_000
_OVER_LIMIT_PACKET_LENGTH = 80_001


def _build_row(
    speaker: Optional[str],
    transcript: str,
    next_transcript: Optional[str],
    person_name: Optional[str] = "A Person",
) -> HandCheckSnapshotRow:
    return HandCheckSnapshotRow(
        speech_id=_SPEECH_ID,
        report_id=_REPORT_ID,
        hansard_report_id=_HANSARD_REPORT_ID,
        html_file_name=None,
        report_version="sprs3",
        report_type="oral-answer",
        parliament_number=14,
        sitting_date=datetime(2010, 5, 5),
        report_title="A Sample Title",
        ordinal=3,
        speaker=speaker,
        speaker_id=_SPEAKER_ID,
        speaker_name="A Speaker Name",
        person_name=person_name,
        kind=SpeechKind.SPEECH,
        transcript=transcript,
        next_speaker=None,
        next_transcript=next_transcript,
    )


def _build_holder(office: str, holder: str) -> HandCheckOfficeHolder:
    return HandCheckOfficeHolder(
        office=office,
        holder=holder,
        form_of_address=HandCheckFormOfAddress.MR,
        first_day=date(2000, 1, 1),
        last_day=None,
        source_url="https://example.org/source",
    )


def _build_report(
    report_id: str, speech_number: int, content: Optional[str] = None
) -> Report:
    return Report(
        volumeNo=14,
        parlNo=14,
        sittingNo=None,
        sittingDate=datetime(2010, 5, 5),
        sno=speech_number,
        original_title="A Sample Title",
        title="A Sample Title",
        reportId=report_id,
        reportType=ReportType.MOTION,
        content=content,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def _build_live_checks(
    differing_count: int,
) -> dict[str, build_hand_check_packets_script.LiveCheck]:
    return {
        f"report-{number:02d}": build_hand_check_packets_script.LiveCheck(
            HandCheckLiveCheckStatus.DIFFERS
            if number < differing_count
            else HandCheckLiveCheckStatus.EQUAL,
            [],
        )
        for number in range(_LIVE_CHECK_REPORT_COUNT)
    }


def _build_packet(
    report_html: str,
    snapshot_row: HandCheckSnapshotRow,
    live_check: Optional[build_hand_check_packets_script.LiveCheck] = None,
    office_holders: Optional[list[HandCheckOfficeHolder]] = None,
    earlier_chair_lines: Optional[
        list[build_hand_check_packets_script.ChairLine]
    ] = None,
) -> HandCheckPacket:
    return build_hand_check_packets_script.build_packet(
        _PACKET_ID,
        snapshot_row,
        build_hand_check_packets_script.split_source_paragraphs(report_html),
        live_check,
        [] if office_holders is None else office_holders,
        [] if earlier_chair_lines is None else earlier_chair_lines,
    )


def _build_joined_row_packet(
    live_check: Optional[build_hand_check_packets_script.LiveCheck] = None,
) -> HandCheckPacket:
    return _build_packet(
        SPRS3_ORAL_ANSWER_HTML,
        _build_row(_MINISTER_LABEL, _JOINED_ROW, _NEXT_ROW),
        live_check,
    )


def _build_committee_packet(
    office_holders: Optional[list[HandCheckOfficeHolder]] = None,
) -> HandCheckPacket:
    return _build_packet(
        SPRS2_COMMITTEE_HTML,
        _build_row("The Chairman", "Order. It is 6.30 pm.", None),
        office_holders=office_holders,
    )


def test_an_answer_with_text_is_text() -> None:
    assert build_hand_check_packets_script.classify_topic_answer(
        HansardTopicResponse(html_content="<p>older</p>"), ReportVersion.SPRS2
    ) == build_hand_check_packets_script.TopicAnswer(
        HandCheckAnswerStatus.TEXT, "<p>older</p>", ""
    )
    assert build_hand_check_packets_script.classify_topic_answer(
        HansardTopicResponse(resultHTML=HansardTopicResultHtml(content="<p>newer</p>")),
        ReportVersion.SPRS3,
    ) == build_hand_check_packets_script.TopicAnswer(
        HandCheckAnswerStatus.TEXT, "<p>newer</p>", ""
    )


@pytest.mark.parametrize(
    ("hansard_topic_response", "report_version"),
    [
        (HansardTopicResponse(), ReportVersion.SPRS2),
        (HansardTopicResponse(html_content=""), ReportVersion.SPRS2),
        (
            HansardTopicResponse(resultHTML=HansardTopicResultHtml(content=None)),
            ReportVersion.SPRS3,
        ),
        (
            HansardTopicResponse(resultHTML=HansardTopicResultHtml(content="")),
            ReportVersion.SPRS3,
        ),
        (HansardTopicResponse(html_content="<p>older</p>"), ReportVersion.SPRS3),
    ],
)
def test_an_answer_with_no_text_in_the_field_of_its_system_is_no_content(
    hansard_topic_response: HansardTopicResponse, report_version: ReportVersion
) -> None:
    assert build_hand_check_packets_script.classify_topic_answer(
        hansard_topic_response, report_version
    ) == build_hand_check_packets_script.TopicAnswer(
        HandCheckAnswerStatus.NO_CONTENT, None, "No content"
    )


def test_an_answer_with_an_error_code_is_an_error_even_when_it_carries_text() -> None:
    assert build_hand_check_packets_script.classify_topic_answer(
        HansardTopicResponse(
            error_code=500,
            description="Unable to process the request.",
            html_content="<p>older</p>",
        ),
        ReportVersion.SPRS2,
    ) == build_hand_check_packets_script.TopicAnswer(
        HandCheckAnswerStatus.ERROR,
        None,
        "Error answer 500: Unable to process the request.",
    )


def test_a_nul_character_in_the_text_is_replaced() -> None:
    topic_answer = build_hand_check_packets_script.classify_topic_answer(
        HansardTopicResponse(html_content="a\x00b"), ReportVersion.SPRS2
    )

    assert topic_answer.text == "a�b"


def test_the_live_check_choice_is_the_same_for_the_same_ids_in_any_order() -> None:
    hansard_report_ids = [f"id-{number:03d}" for number in range(200)]

    assert build_hand_check_packets_script.get_live_check_hansard_report_ids(
        hansard_report_ids
    ) == build_hand_check_packets_script.get_live_check_hansard_report_ids(
        list(reversed(hansard_report_ids))
    )


def test_the_live_check_takes_fifty_distinct_reports_from_more_than_fifty() -> None:
    hansard_report_ids = [f"id-{number:03d}" for number in range(120)]

    chosen_hansard_report_ids = (
        build_hand_check_packets_script.get_live_check_hansard_report_ids(
            [*hansard_report_ids, *hansard_report_ids]
        )
    )

    assert len(chosen_hansard_report_ids) == _LIVE_CHECK_REPORT_COUNT
    assert len(set(chosen_hansard_report_ids)) == _LIVE_CHECK_REPORT_COUNT
    assert set(chosen_hansard_report_ids) <= set(hansard_report_ids)


def test_the_live_check_takes_every_report_when_there_are_fewer_than_fifty() -> None:
    hansard_report_ids = [
        f"id-{number:02d}" for number in range(_LIVE_CHECK_REPORT_COUNT)
    ]

    assert sorted(
        build_hand_check_packets_script.get_live_check_hansard_report_ids(
            ["b", "a", "c", "a"]
        )
    ) == ["a", "b", "c"]
    assert (
        sorted(
            build_hand_check_packets_script.get_live_check_hansard_report_ids(
                hansard_report_ids
            )
        )
        == hansard_report_ids
    )


def test_the_live_check_choice_follows_the_committed_seed() -> None:
    hansard_report_ids = [f"id-{number:03d}" for number in range(200)]

    assert build_hand_check_packets_script.get_live_check_hansard_report_ids(
        hansard_report_ids
    ) == random.Random(20_261_105).sample(
        sorted(hansard_report_ids), _LIVE_CHECK_REPORT_COUNT
    )


def test_stored_texts_come_back_by_sprs_id() -> None:
    reports = [_build_report("A", 1, "<p>a</p>"), _build_report("B", 2, "<p>b</p>")]

    assert build_hand_check_packets_script.get_validated_stored_texts(
        ["A", "B"], reports
    ) == {"A": "<p>a</p>", "B": "<p>b</p>"}


def test_missing_or_empty_stored_text_stops_the_build_and_the_message_counts_it() -> (
    None
):
    reports = [
        _build_report("A", 1, "<p>a</p>"),
        _build_report("B", 2, None),
        _build_report("C", 3, ""),
    ]

    with pytest.raises(
        HansardHandCheckError, match="missing or empty for 2 of 3 reports"
    ):
        build_hand_check_packets_script.get_validated_stored_texts(
            ["A", "B", "C"], reports
        )


def test_a_report_the_database_did_not_return_stops_the_build() -> None:
    with pytest.raises(
        HansardHandCheckError, match="missing or empty for 1 of 1 reports"
    ):
        build_hand_check_packets_script.get_validated_stored_texts(["A"], [])


def test_a_live_text_equal_to_the_stored_text_is_equal() -> None:
    assert build_hand_check_packets_script.get_live_check(
        "<p>a</p>", "<p>a</p>"
    ) == build_hand_check_packets_script.LiveCheck(HandCheckLiveCheckStatus.EQUAL, [])


def test_a_live_text_that_differs_keeps_its_paragraphs_for_the_match_against_it() -> (
    None
):
    live_check = build_hand_check_packets_script.get_live_check("<p>b</p>", "<p>a</p>")

    assert live_check.status == HandCheckLiveCheckStatus.DIFFERS
    assert live_check.live_paragraphs == (
        build_hand_check_packets_script.split_source_paragraphs("<p>b</p>")
    )


def test_a_nul_in_the_live_answer_equals_a_replacement_character_in_the_stored_copy() -> (
    None
):
    topic_answer = build_hand_check_packets_script.classify_topic_answer(
        HansardTopicResponse(html_content="<p>a\x00b</p>"), ReportVersion.SPRS2
    )

    assert topic_answer.text is not None
    assert (
        build_hand_check_packets_script.get_live_check(
            topic_answer.text, "<p>a�b</p>"
        ).status
        == HandCheckLiveCheckStatus.EQUAL
    )


def test_two_differing_reports_do_not_stop_the_build() -> None:
    build_hand_check_packets_script.validate_can_build_after_live_check(
        _build_live_checks(2)
    )


def test_more_than_two_differing_reports_stop_the_build() -> None:
    with pytest.raises(HansardHandCheckError, match="3 of 50 live-checked reports"):
        build_hand_check_packets_script.validate_can_build_after_live_check(
            _build_live_checks(3)
        )


def test_packet_ids_are_distinct_twelve_digit_hex_strings() -> None:
    packet_ids = build_hand_check_packets_script.get_packet_ids(_PACKET_ID_COUNT)

    assert len(packet_ids) == _PACKET_ID_COUNT
    assert len(set(packet_ids)) == _PACKET_ID_COUNT
    for packet_id in packet_ids:
        assert len(packet_id) == _PACKET_ID_LENGTH
        int(packet_id, _HEXADECIMAL_BASE)


def test_no_packet_ids_are_drawn_for_no_packets() -> None:
    assert build_hand_check_packets_script.get_packet_ids(0) == []


def test_earlier_reports_come_nearest_first_by_speech_number_then_report_id() -> None:
    report_a = _build_report("a", 1)
    report_b = _build_report("b", 2)
    report_c = _build_report("c", 2)
    report_d = _build_report("d", 3)
    sitting_reports = [report_d, report_c, report_a, report_b]

    assert build_hand_check_packets_script.get_earlier_reports(
        sitting_reports, report_c
    ) == [report_b, report_a]
    assert build_hand_check_packets_script.get_earlier_reports(
        sitting_reports, report_b
    ) == [report_a]
    assert (
        build_hand_check_packets_script.get_earlier_reports(sitting_reports, report_a)
        == []
    )


def test_one_hundred_and_twenty_five_short_packets_fill_batches_of_fifty_in_order() -> (
    None
):
    rendered_packets = [f"packet {number}" for number in range(125)]

    batches = build_hand_check_packets_script.get_batches(rendered_packets)

    assert [len(batch) for batch in batches] == _BATCH_SIZES
    assert [
        rendered_packet for batch in batches for rendered_packet in batch
    ] == rendered_packets


def test_a_batch_closes_before_it_passes_eighty_thousand_characters() -> None:
    first, second, third = (letter * _LONG_PACKET_LENGTH for letter in ("a", "b", "c"))

    assert build_hand_check_packets_script.get_batches([first, second, third]) == [
        [first, second],
        [third],
    ]


def test_a_batch_may_hold_exactly_eighty_thousand_characters() -> None:
    first = "a" * _HALF_LIMIT_PACKET_LENGTH
    second = "b" * _HALF_LIMIT_PACKET_LENGTH

    assert build_hand_check_packets_script.get_batches([first, second]) == [
        [first, second]
    ]


def test_a_packet_longer_than_the_limit_gets_a_batch_of_its_own() -> None:
    long_packet = "a" * _OVER_LIMIT_PACKET_LENGTH

    assert build_hand_check_packets_script.get_batches(
        ["first", "second", long_packet, "third"]
    ) == [["first", "second"], [long_packet], ["third"]]


def test_no_packets_make_no_batches() -> None:
    assert build_hand_check_packets_script.get_batches([]) == []


def test_an_exact_row_in_a_report_with_a_next_row_makes_a_full_packet() -> None:
    snapshot_row = _build_row(_MINISTER_LABEL, _JOINED_ROW, _NEXT_ROW)

    packet = _build_packet(SPRS3_ORAL_ANSWER_HTML, snapshot_row)

    assert packet.packet_id == _PACKET_ID
    assert packet.snapshot == snapshot_row
    assert packet.official_record_url == _OFFICIAL_RECORD_URL
    assert packet.match_status == HandCheckMatchStatus.EXACT
    assert packet.word_differences == []
    assert len(packet.context_paragraphs) == _JOINED_ROW_CONTEXT_PARAGRAPH_COUNT
    assert packet.after_paragraph is not None
    assert packet.gap_check is not None
    assert packet.gap_check.is_next_row is True
    assert packet.role_section is None
    assert packet.live_check_status is None
    assert packet.live_match_status is None


def test_an_inexact_row_lists_its_word_differences() -> None:
    packet = _build_packet(
        SPRS3_ORAL_ANSWER_HTML, _build_row(_MINISTER_LABEL, _INEXACT_ROW, _NEXT_ROW)
    )

    assert packet.match_status == HandCheckMatchStatus.INEXACT
    assert packet.word_differences == [
        HandCheckWordDifference(operation="delete", source_words="the", row_words="")
    ]


def test_a_row_found_nowhere_makes_a_packet_with_nothing_from_the_source() -> None:
    packet = _build_packet(
        SPRS3_ORAL_ANSWER_HTML,
        _build_row(_MINISTER_LABEL, "Words that the report never prints.", None),
    )

    assert packet.match_status == HandCheckMatchStatus.NOT_FOUND
    assert packet.matched_source_html == ""
    assert packet.context_paragraphs == []
    assert packet.word_differences == []
    assert packet.after_paragraph is None
    assert packet.gap_check is None


def test_a_live_text_that_differs_gives_the_status_and_the_rows_match_status_against_it() -> (
    None
):
    packet = _build_joined_row_packet(
        build_hand_check_packets_script.LiveCheck(
            HandCheckLiveCheckStatus.DIFFERS,
            build_hand_check_packets_script.split_source_paragraphs(
                "<p>Some other live text.</p>"
            ),
        )
    )

    assert packet.live_check_status == HandCheckLiveCheckStatus.DIFFERS
    assert packet.live_match_status == HandCheckMatchStatus.NOT_FOUND
    assert packet.match_status == HandCheckMatchStatus.EXACT


def test_an_equal_live_text_gives_the_status_and_no_live_match_status() -> None:
    packet = _build_joined_row_packet(
        build_hand_check_packets_script.LiveCheck(HandCheckLiveCheckStatus.EQUAL, [])
    )

    assert packet.live_check_status == HandCheckLiveCheckStatus.EQUAL
    assert packet.live_match_status is None


def test_an_office_label_makes_a_role_section_from_the_table() -> None:
    prime_minister = _build_holder("Prime Minister", "A Holder")

    packet = _build_packet(
        _OFFICE_HTML,
        _build_row("The Prime Minister", "Thank you, Mr Speaker.", None),
        office_holders=[prime_minister],
    )

    assert packet.role_section is not None
    assert packet.role_section.is_chair_label is False
    assert packet.role_section.office == "Prime Minister"
    assert packet.role_section.office_holders == [prime_minister]
    assert packet.role_section.chair_marks == []


def test_a_chair_label_takes_the_marks_of_its_own_report_before_and_after_the_row() -> (
    None
):
    speaker = _build_holder("Speaker", "A Holder")

    packet = _build_committee_packet([speaker])

    assert packet.role_section is not None
    assert packet.role_section.is_chair_label is True
    assert packet.role_section.office_holders == [speaker]
    assert packet.role_section.chair_marks == [
        "Last mark before the row: " + _TAG_LINE + " (report: A Sample Title)",
        "First mark after the row: " + _THEREUPON_LINE + " (report: A Sample Title)",
    ]


def test_a_chair_label_with_no_mark_before_it_in_its_report_takes_the_earlier_reports_lines() -> (
    None
):
    packet = _build_packet(
        "<p><b>The Chairman:</b> Order.</p>",
        _build_row("The Chairman", "Order.", None),
        earlier_chair_lines=[
            build_hand_check_packets_script.ChairLine(
                "[Mr Speaker in the Chair]", True, "Earlier Title"
            ),
            build_hand_check_packets_script.ChairLine(
                "Sitting suspended at 4.00 pm.", False, "Earlier Title"
            ),
        ],
    )

    assert packet.role_section is not None
    assert packet.role_section.chair_marks == [
        "Last mark before the row: [Mr Speaker in the Chair] (report: Earlier Title)",
        "Between that mark and the row: Sitting suspended at 4.00 pm. (report: Earlier Title)",
    ]


def test_a_mark_before_the_row_in_its_own_report_leaves_the_earlier_reports_lines_out() -> (
    None
):
    packet = _build_packet(
        "<p><b>Mr Speaker:</b> Order.</p><p><b>The Chairman:</b> Yes.</p>",
        _build_row("The Chairman", "Yes.", None),
        earlier_chair_lines=[
            build_hand_check_packets_script.ChairLine(
                "[Mr Deputy Speaker in the Chair]", True, "Earlier Title"
            )
        ],
    )

    assert packet.role_section is not None
    assert packet.role_section.chair_marks == [
        "Last mark before the row: Mr Speaker: (report: A Sample Title)"
    ]


def test_a_bare_deputy_label_on_a_day_with_two_deputies_is_not_a_chair_mark() -> None:
    packet = _build_packet(
        _TWO_DEPUTIES_HTML,
        _build_row("The Chairman", "Yes.", None),
        office_holders=[
            _build_holder("Deputy Speaker", "Charles Chong"),
            _build_holder("Deputy Speaker", "Lim Biow Chuan"),
        ],
    )

    assert packet.role_section is not None
    assert packet.role_section.chair_marks == [
        "Last mark before the row: [Mr Deputy Speaker in the Chair] (report: A Sample Title)"
    ]


def test_a_row_with_no_label_has_no_role_section() -> None:
    packet = _build_packet(
        SPRS3_ORAL_ANSWER_HTML, _build_row(None, _JOINED_ROW, _NEXT_ROW)
    )

    assert packet.role_section is None


def test_the_records_file_and_the_reader_batches_go_to_separate_trees(
    tmp_path: Path,
) -> None:
    packet = _build_joined_row_packet()
    build_directory = tmp_path / "build"

    directory_name_to_batch_count = (
        build_hand_check_packets_script.write_hand_check_packets(
            [packet], build_directory
        )
    )

    assert directory_name_to_batch_count == {"sonnet": 1, "opus": 1}
    assert sorted(path.name for path in build_directory.iterdir()) == [
        "batches",
        "records",
    ]
    records_directory = build_directory / "records"
    assert [path.name for path in records_directory.iterdir()] == ["packets.json"]
    assert HandCheckPackets.model_validate_json(
        (records_directory / "packets.json").read_text(encoding="utf-8")
    ).root == [packet]
    batches_directory = build_directory / "batches"
    assert sorted(path.name for path in batches_directory.iterdir()) == [
        "opus",
        "sonnet",
    ]
    for reader_directory_name, is_for_sonnet in (("sonnet", True), ("opus", False)):
        reader_directory = batches_directory / reader_directory_name
        assert [path.name for path in reader_directory.iterdir()] == ["batch-001"]
        batch_directory = reader_directory / "batch-001"
        assert [path.name for path in batch_directory.iterdir()] == ["packets.md"]
        assert (batch_directory / "packets.md").read_text(
            encoding="utf-8"
        ) == build_hand_check_packets_script.render_batch(
            [
                build_hand_check_packets_script.render_packet(
                    packet, is_for_sonnet=is_for_sonnet
                )
            ],
            is_for_sonnet=is_for_sonnet,
        )


def test_a_build_into_an_existing_directory_is_refused(tmp_path: Path) -> None:
    packet = _build_joined_row_packet()

    with pytest.raises(FileExistsError):
        build_hand_check_packets_script.write_hand_check_packets([packet], tmp_path)
    assert list(tmp_path.iterdir()) == []

    build_hand_check_packets_script.write_hand_check_packets(
        [packet], tmp_path / "build"
    )
    with pytest.raises(FileExistsError):
        build_hand_check_packets_script.write_hand_check_packets(
            [packet], tmp_path / "build"
        )


def test_a_rendered_packet_shows_none_of_the_ids_or_the_kind() -> None:
    packet = _build_joined_row_packet()

    for is_for_sonnet in (True, False):
        rendered_packet = build_hand_check_packets_script.render_packet(
            packet, is_for_sonnet
        ).replace(packet.official_record_url, "")
        for hidden_text in ("9876543", "8765432", "7654321", "00123456-ZZ", "SPEECH"):
            assert hidden_text not in rendered_packet


def test_a_sonnet_packet_has_the_parts_the_reader_instructions_name_in_order() -> None:
    packet = _build_packet(
        SPRS3_ORAL_ANSWER_HTML,
        _build_row(_MINISTER_LABEL, _INEXACT_ROW, _NEXT_ROW),
        build_hand_check_packets_script.LiveCheck(HandCheckLiveCheckStatus.EQUAL, []),
    )

    rendered_packet = build_hand_check_packets_script.render_packet(
        packet, is_for_sonnet=True
    )

    headings = [
        "## Packet abc123def456",
        "### Label and credited person",
        "### Report",
        "### Snapshot text",
        "### Context",
        "### Match status and Matched source",
        "### Word differences",
        "### Gap check",
        "### Official record link",
        "### Live check note",
    ]
    heading_positions = [rendered_packet.index(heading) for heading in headings]
    assert heading_positions == sorted(heading_positions)
    assert "### Role section" not in rendered_packet
    assert f"Label: {_MINISTER_LABEL}" in rendered_packet
    assert "Credited to: A Speaker Name" in rendered_packet
    assert "Linked person: A Person" in rendered_packet
    assert "Sitting date: 5 May 2010" in rendered_packet
    assert "Status: inexact" in rendered_packet
    assert "SPRS answered" not in rendered_packet


def test_a_sonnet_packet_shows_the_source_with_its_display_markers_and_each_word_difference_numbered() -> (
    None
):
    packet = _build_packet(
        _SUPERSCRIPT_HTML, _build_row("Mr A", _SUPERSCRIPT_ROW, None)
    )

    rendered_packet = build_hand_check_packets_script.render_packet(
        packet, is_for_sonnet=True
    )

    assert "Status: inexact" in rendered_packet
    assert "248<SUP>1</SUP>" in rendered_packet
    assert '1. replace: source "2481", snapshot "248[1]"' in rendered_packet


def test_an_opus_packet_never_shows_the_word_differences_part() -> None:
    packet = _build_packet(
        _SUPERSCRIPT_HTML, _build_row("Mr A", _SUPERSCRIPT_ROW, None)
    )

    rendered_packet = build_hand_check_packets_script.render_packet(
        packet, is_for_sonnet=False
    )

    assert "Status: inexact" in rendered_packet
    assert "248<SUP>1</SUP>" in rendered_packet
    assert "### Word differences" not in rendered_packet
    assert 'source "2481"' not in rendered_packet


def test_a_sonnet_packet_shows_word_differences_only_when_inexact_and_numbers_each_one() -> (
    None
):
    exact_packet = _build_joined_row_packet()
    not_found_packet = _build_packet(
        SPRS3_ORAL_ANSWER_HTML,
        _build_row(_MINISTER_LABEL, "Words that the report never prints.", None),
    )
    inexact_packet = _build_packet(
        SPRS3_ORAL_ANSWER_HTML, _build_row(_MINISTER_LABEL, _INEXACT_ROW, _NEXT_ROW)
    )
    inexact_packet_with_no_differences = inexact_packet.model_copy(
        update={"word_differences": []}
    )
    inexact_packet_with_two_differences = inexact_packet.model_copy(
        update={
            "word_differences": [
                HandCheckWordDifference(
                    operation="delete", source_words="the", row_words=""
                ),
                HandCheckWordDifference(
                    operation="insert", source_words="", row_words="also"
                ),
            ]
        }
    )

    for packet in (exact_packet, not_found_packet, inexact_packet_with_no_differences):
        assert "### Word differences" not in (
            build_hand_check_packets_script.render_packet(packet, is_for_sonnet=True)
        )
    rendered_packet = build_hand_check_packets_script.render_packet(
        inexact_packet_with_two_differences, is_for_sonnet=True
    )
    first_line = '1. delete: source "the", snapshot ""'
    second_line = '2. insert: source "", snapshot "also"'
    assert first_line in rendered_packet
    assert second_line in rendered_packet
    assert rendered_packet.index(first_line) < rendered_packet.index(second_line)


def test_a_rendered_chair_packet_lists_the_marks_and_a_rendered_office_packet_lists_the_holders() -> (
    None
):
    holder_line = (
        "- A Holder (MR), 2000-01-01 to no end date, source https://example.org/source"
    )

    rendered_chair_packet = build_hand_check_packets_script.render_packet(
        _build_committee_packet(), is_for_sonnet=False
    )
    rendered_chair_packet_with_speaker = build_hand_check_packets_script.render_packet(
        _build_committee_packet([_build_holder("Speaker", "A Holder")]),
        is_for_sonnet=False,
    )
    rendered_office_packet = build_hand_check_packets_script.render_packet(
        _build_packet(
            _OFFICE_HTML,
            _build_row("The Prime Minister", "Thank you, Mr Speaker.", None),
            office_holders=[_build_holder("Prime Minister", "A Holder")],
        ),
        is_for_sonnet=False,
    )

    assert "Chair label." in rendered_chair_packet
    assert (
        "- Last mark before the row: " + _TAG_LINE + " (report: A Sample Title)"
        in rendered_chair_packet
    )
    assert "No entry in the table." in rendered_chair_packet
    assert "Chair label." in rendered_chair_packet_with_speaker
    assert holder_line in rendered_chair_packet_with_speaker
    assert "Office label: Prime Minister." in rendered_office_packet
    assert holder_line in rendered_office_packet


def test_a_rendered_packet_with_an_equal_live_check_gives_the_equal_sentence() -> None:
    rendered_packet = build_hand_check_packets_script.render_packet(
        _build_joined_row_packet(
            build_hand_check_packets_script.LiveCheck(
                HandCheckLiveCheckStatus.EQUAL, []
            )
        ),
        is_for_sonnet=True,
    )

    assert "### Live check note" in rendered_packet
    assert (
        "Today's SPRS text equals the stored copy this packet is built from."
        in rendered_packet
    )
    assert "match status is" not in rendered_packet


def test_a_rendered_packet_with_a_differing_live_check_says_so_and_gives_the_live_match_status() -> (
    None
):
    rendered_packet = build_hand_check_packets_script.render_packet(
        _build_joined_row_packet(
            build_hand_check_packets_script.LiveCheck(
                HandCheckLiveCheckStatus.DIFFERS,
                build_hand_check_packets_script.split_source_paragraphs(
                    "<p>Some other live text.</p>"
                ),
            )
        ),
        is_for_sonnet=True,
    )

    assert (
        "Today's SPRS text differs from the stored copy this packet is built from."
        in rendered_packet
    )
    assert "Against today's SPRS text the match status is not found." in rendered_packet


def test_a_rendered_packet_outside_the_live_check_has_no_live_check_note() -> None:
    rendered_packet = build_hand_check_packets_script.render_packet(
        _build_joined_row_packet(), is_for_sonnet=True
    )

    assert "Live check note" not in rendered_packet
    assert "Today's SPRS text" not in rendered_packet


def test_a_rendered_batch_starts_with_the_markup_legend_and_holds_every_packet() -> (
    None
):
    first_packet = "## Packet first"
    second_packet = "## Packet second"
    word_differences_legend = "A Word differences part numbers the differences the script found between the source text and the snapshot text, one per line."

    sonnet_batch = build_hand_check_packets_script.render_batch(
        [first_packet, second_packet], is_for_sonnet=True
    )
    opus_batch = build_hand_check_packets_script.render_batch(
        [first_packet, second_packet], is_for_sonnet=False
    )

    for rendered_batch in (sonnet_batch, opus_batch):
        assert rendered_batch.startswith("# Packets")
        assert (
            "<B>...</B> marks bold, <I>...</I> italic, <SUP>...</SUP> raised text and <SUB>...</SUB> lowered text"
            in rendered_batch
        )
        assert (
            "Snapshot text is shown as the database stores it, with its own markers."
            in rendered_batch
        )
        assert rendered_batch.index(first_packet) < rendered_batch.index(second_packet)
        assert rendered_batch.endswith("\n")
    assert word_differences_legend in sonnet_batch
    assert word_differences_legend not in opus_batch
