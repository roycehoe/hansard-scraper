import json
from typing import Optional

from crud.sitting import SittingAttendanceTextRow
from database.speaker import Speaker
from enums import LeaveSpeakerLinkSource
from services.attendance import (
    EntryName,
    build_speaker_lookups,
    get_sitting_entry_names,
)
from services.leave_period import LeaveEntrySpeakerLink, get_leave_entry_speaker_link
from utils.leave_entry import get_leave_name_key

_PARLIAMENT_NUMBER = 14
_LEE_SPEAKER_ID = 1
_ISWARAN_SPEAKER_ID = 2
_FIRST_ISWARAN_SPEAKER_ID = 3
_SECOND_ISWARAN_SPEAKER_ID = 4


def _build_speaker(name: str) -> Speaker:
    return Speaker(
        name=name,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )


_SPEAKERS = [
    _build_speaker("Lee Hsien Loong"),
    _build_speaker("S. Iswaran"),
    _build_speaker("Tan Wu Meng"),
    _build_speaker("Tan Wu Meng"),
]
_LOOKUPS = build_speaker_lookups(_SPEAKERS)
_NAME_PARLIAMENT_NUMBER_TO_SPEAKER_ID = {
    ("Lee Hsien Loong", _PARLIAMENT_NUMBER): _LEE_SPEAKER_ID,
    ("S. Iswaran", _PARLIAMENT_NUMBER): _ISWARAN_SPEAKER_ID,
}


def _get_link(
    name: str,
    entry_name_key_to_speaker_ids: Optional[dict[str, list[Optional[int]]]] = None,
    parliament_number: Optional[int] = _PARLIAMENT_NUMBER,
) -> Optional[LeaveEntrySpeakerLink]:
    return get_leave_entry_speaker_link(
        name,
        parliament_number,
        _LOOKUPS,
        _NAME_PARLIAMENT_NUMBER_TO_SPEAKER_ID,
        entry_name_key_to_speaker_ids or {},
    )


def test_rule_a_links_a_name_with_a_title() -> None:
    assert _get_link("Mr Lee Hsien Loong") == LeaveEntrySpeakerLink(
        _LEE_SPEAKER_ID, LeaveSpeakerLinkSource.ROSTER_NAME
    )


def test_rule_a_links_initials_with_periods() -> None:
    assert _get_link("Mr S Iswaran") == LeaveEntrySpeakerLink(
        _ISWARAN_SPEAKER_ID, LeaveSpeakerLinkSource.ROSTER_NAME
    )


def test_a_name_held_by_two_speakers_falls_through_to_rule_b() -> None:
    entry_name_key_to_speaker_ids: dict[str, list[Optional[int]]] = {
        get_leave_name_key("Tan Wu Meng"): [_FIRST_ISWARAN_SPEAKER_ID]
    }

    assert _get_link("Dr Tan Wu Meng", entry_name_key_to_speaker_ids) == (
        LeaveEntrySpeakerLink(
            _FIRST_ISWARAN_SPEAKER_ID, LeaveSpeakerLinkSource.SITTING_ATTENDANCE_ENTRY
        )
    )


def test_rule_b_links_one_entry() -> None:
    entry_name_key_to_speaker_ids: dict[str, list[Optional[int]]] = {
        get_leave_name_key("Mr Louis Chua"): [9]
    }

    assert _get_link("Louis Chua", entry_name_key_to_speaker_ids) == (
        LeaveEntrySpeakerLink(9, LeaveSpeakerLinkSource.SITTING_ATTENDANCE_ENTRY)
    )


def test_two_entries_with_one_key_link_nothing() -> None:
    entry_name_key_to_speaker_ids: dict[str, list[Optional[int]]] = {
        get_leave_name_key("Tan Wu Meng"): [
            _FIRST_ISWARAN_SPEAKER_ID,
            _SECOND_ISWARAN_SPEAKER_ID,
        ]
    }

    assert _get_link("Tan Wu Meng", entry_name_key_to_speaker_ids) is None


def test_an_entry_whose_attendance_row_has_no_id_links_nothing() -> None:
    entry_name_key_to_speaker_ids: dict[str, list[Optional[int]]] = {
        get_leave_name_key("Louis Chua"): [None]
    }

    assert _get_link("Louis Chua", entry_name_key_to_speaker_ids) is None


def test_a_name_with_no_match_gives_none() -> None:
    assert _get_link("Mr Nobody Known") is None


def test_a_surname_alone_gives_none() -> None:
    assert _get_link("Lee") is None
    assert _get_link("Iswaran") is None


def test_a_name_missing_its_last_word_gives_none() -> None:
    assert _get_link("Lee Hsien") is None


def test_a_name_with_no_known_parliament_skips_rule_a() -> None:
    assert _get_link("Mr Lee Hsien Loong", parliament_number=None) is None


def _build_sitting_attendance_text_row(
    markdown_content: Optional[str], attendance_list: Optional[str]
) -> SittingAttendanceTextRow:
    return SittingAttendanceTextRow(
        id=1,
        sitting_date="2-4-2025",
        parlement_no=_PARLIAMENT_NUMBER,
        volume_no=None,
        markdown_content=markdown_content,
        attendance_list=attendance_list,
    )


def test_get_sitting_entry_names_on_a_markdown_sitting_gives_the_printed_names() -> (
    None
):
    markdown_content = (
        "PRESENT:\n"
        "Mr Lee Hsien Loong (Ang Mo Kio).\n"
        "ABSENT:\n"
        "Mr Nobody Known (Nowhere).\n"
    )

    entry_names = get_sitting_entry_names(
        _build_sitting_attendance_text_row(markdown_content, None), _LOOKUPS
    )

    assert entry_names == [
        EntryName("Lee Hsien Loong", "Lee Hsien Loong"),
        EntryName("Nobody Known", "Nobody Known"),
    ]


def test_get_sitting_entry_names_on_a_list_sitting_gives_the_printed_names() -> None:
    attendance_list = json.dumps(
        [
            {"mpName": "Mr S Iswaran (West Coast)", "attendance": True},
            {"mpName": None, "attendance": True},
        ]
    )

    entry_names = get_sitting_entry_names(
        _build_sitting_attendance_text_row(None, attendance_list), _LOOKUPS
    )

    assert [entry_name.printed_name for entry_name in entry_names] == ["S Iswaran"]
    assert [entry_name.speaker_name for entry_name in entry_names] == ["S. Iswaran"]
