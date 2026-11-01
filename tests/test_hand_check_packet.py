from datetime import date, datetime

import pytest
from pydantic import ValidationError

from enums import (
    HandCheckFormOfAddress,
    HandCheckLiveCheckStatus,
    HandCheckMatchStatus,
    SpeechKind,
)
from schemas.hand_check_office_holder import HandCheckOfficeHolder
from schemas.hand_check_packet import (
    HandCheckGapCheck,
    HandCheckPacket,
    HandCheckPackets,
    HandCheckRoleSection,
    HandCheckWordDifference,
)
from schemas.hand_check_snapshot import HandCheckSnapshotRow


def _build_snapshot_row() -> HandCheckSnapshotRow:
    return HandCheckSnapshotRow(
        speech_id=1,
        report_id=2,
        hansard_report_id="00069257-ZZ.00055026-ZZ_1#id003_19720322_S0007_T00171-speaker#",
        html_file_name=None,
        report_version="sprs3",
        report_type="speaker",
        parliament_number=3,
        sitting_date=datetime(1972, 3, 22),
        report_title="A title",
        ordinal=3,
        speaker="Mr Speaker",
        speaker_id=7,
        speaker_name="A Speaker",
        person_name="A Speaker",
        kind=SpeechKind.SPEECH,
        transcript="Some text.",
        next_speaker=None,
        next_transcript=None,
    )


def _build_full_packet() -> HandCheckPacket:
    return HandCheckPacket(
        packet_id="P0001",
        snapshot=_build_snapshot_row(),
        official_record_url="https://sprs.parl.gov.sg/search/#/sprs3topic?reportid=speaker",
        match_status=HandCheckMatchStatus.INEXACT,
        matched_source_html="<p>Some text 2481.</p>",
        context_paragraphs=["Before.", "Some text 2481."],
        after_paragraph="After.",
        word_differences=[
            HandCheckWordDifference(
                operation="replace", source_words="2481", row_words="248[1]"
            )
        ],
        gap_check=HandCheckGapCheck(
            is_next_row=False,
            skipped_paragraphs=["Column: 303"],
            next_source_text="Next text.",
        ),
        role_section=HandCheckRoleSection(
            is_chair_label=False,
            office="Speaker",
            office_holders=[
                HandCheckOfficeHolder(
                    office="Speaker",
                    holder="A Speaker",
                    form_of_address=HandCheckFormOfAddress.MR,
                    first_day=date(1970, 1, 1),
                    last_day=None,
                    source_url="https://example.org/speaker",
                )
            ],
            chair_marks=[],
        ),
        live_check_status=HandCheckLiveCheckStatus.DIFFERS,
        live_match_status=HandCheckMatchStatus.EXACT,
    )


def _build_bare_packet() -> HandCheckPacket:
    return HandCheckPacket(
        packet_id="P0002",
        snapshot=_build_snapshot_row(),
        official_record_url="https://sprs.parl.gov.sg/search/#/sprs3topic?reportid=speaker",
        match_status=HandCheckMatchStatus.NOT_FOUND,
        matched_source_html="",
        context_paragraphs=[],
        after_paragraph=None,
        word_differences=[],
        gap_check=None,
        role_section=None,
        live_check_status=None,
        live_match_status=None,
    )


def test_a_full_packet_list_reads_back_equal_after_a_round_trip() -> None:
    packets = HandCheckPackets([_build_full_packet()])

    assert HandCheckPackets.model_validate_json(packets.model_dump_json()) == packets


def test_a_packet_with_every_optional_field_empty_reads_back_equal() -> None:
    packets = HandCheckPackets([_build_bare_packet()])

    assert HandCheckPackets.model_validate_json(packets.model_dump_json()) == packets


@pytest.mark.parametrize("match_status", ["PARTIAL", "exact"])
def test_a_packet_refuses_an_unlisted_match_status(match_status: str) -> None:
    packet_fields = _build_full_packet().model_dump(mode="json")
    packet_fields["match_status"] = match_status

    with pytest.raises(ValidationError):
        HandCheckPacket.model_validate(packet_fields)


def test_a_packet_refuses_an_unlisted_live_check_status() -> None:
    packet_fields = _build_full_packet().model_dump(mode="json")
    packet_fields["live_check_status"] = "SAME"

    with pytest.raises(ValidationError):
        HandCheckPacket.model_validate(packet_fields)


@pytest.mark.parametrize("field_name", list(HandCheckPacket.model_fields))
def test_a_packet_refuses_a_missing_field(field_name: str) -> None:
    packet_fields = _build_bare_packet().model_dump(mode="json")
    del packet_fields[field_name]

    with pytest.raises(ValidationError):
        HandCheckPacket.model_validate(packet_fields)


def test_a_word_difference_inside_a_packet_is_checked_too() -> None:
    packet_fields = _build_full_packet().model_dump(mode="json")
    packet_fields["word_differences"] = [{"operation": "delete", "source_words": "two"}]

    with pytest.raises(ValidationError):
        HandCheckPacket.model_validate(packet_fields)


def test_the_match_and_live_check_status_values_equal_their_member_names() -> None:
    assert [status.value for status in HandCheckMatchStatus] == [
        "EXACT",
        "INEXACT",
        "NOT_FOUND",
    ]
    assert [status.value for status in HandCheckLiveCheckStatus] == [
        "EQUAL",
        "DIFFERS",
    ]
