import json
from pathlib import Path
from typing import Optional

import pytest

from database.attendance import Attendance
from enums import AttendanceCleanupReason
from exceptions import HansardWriteCheckError
from schemas.attendance_cleanup import (
    AttendanceCleanup,
    AttendanceCorrection,
    AttendanceRemoval,
    AttendanceSpeakerRole,
)
from schemas.speaker import SpeakerResult
from services.attendance_cleanup import AttendanceUpdate, build_attendance_cleanup_plan
from utils.sitting_dates import parse_sitting_date
from utils.speaker_terms import SPEAKER_TERMS

_DATA_FILE = Path(__file__).parent.parent / "data" / "attendance_cleanup.json"
_REMOVAL_COUNT = 91
_CORRECTION_COUNT = 14
_SPEAKER_ROLE_COUNT = 13
_HOLDER_ID = 7
_HOLDER_NAME = "George Oehlers"


def _get_file_cleanup() -> AttendanceCleanup:
    return AttendanceCleanup.model_validate(json.loads(_DATA_FILE.read_text()))


def _get_members(file_name: str) -> list[SpeakerResult]:
    return [SpeakerResult.model_validate(record) for record in json.loads((_DATA_FILE.parent / file_name).read_text())]


def _get_row(id: int, speaker_name: str = "Someone", is_present: bool = True, location_name: Optional[str] = None, speaker_id: Optional[int] = None, sitting_id: int = 1) -> Attendance:
    return Attendance(id=id, sitting_id=sitting_id, speaker_name=speaker_name, is_present=is_present, location_name=location_name, speaker_id=speaker_id)


def _get_removal(id: int, speaker_name: str = "Someone", is_present: bool = True, sitting_id: int = 1) -> AttendanceRemoval:
    return AttendanceRemoval(id=id, sitting_id=sitting_id, speaker_name=speaker_name, is_present=is_present, reason=AttendanceCleanupReason.NOT_A_NAME)


def _get_role(id: int, sitting_id: int = 1) -> AttendanceSpeakerRole:
    return AttendanceSpeakerRole(id=id, sitting_id=sitting_id, sitting_date="23-12-1960", speaker_name="Speaker", is_present=True, location_name="Sir George Oehlers, O.B.E.")


def _get_correction(id: int) -> AttendanceCorrection:
    return AttendanceCorrection(
        id=id, sitting_id=1, speaker_name="Wong Lm Ken", is_present=True, location_name="Alexandra",
        speaker_name_after="Wong Lin Ken", location_name_after="Alexandra", reason=AttendanceCleanupReason.OCR_ALIAS,
    )


def test_cleanup_file_holds_each_row_once_with_a_reason_of_its_own_kind() -> None:
    cleanup = _get_file_cleanup()

    entry_ids = [entry.id for entry in (*cleanup.removals, *cleanup.corrections, *cleanup.speaker_roles)]
    assert len(set(entry_ids)) == len(entry_ids)
    assert (len(cleanup.removals), len(cleanup.corrections), len(cleanup.speaker_roles)) == (_REMOVAL_COUNT, _CORRECTION_COUNT, _SPEAKER_ROLE_COUNT)
    assert {removal.reason for removal in cleanup.removals} == {
        AttendanceCleanupReason.NOT_A_NAME,
        AttendanceCleanupReason.OFFICE_FRAGMENT,
        AttendanceCleanupReason.REPEATED_ATTENDEE,
    }
    assert {correction.reason for correction in cleanup.corrections} == {
        AttendanceCleanupReason.OCR_ALIAS,
        AttendanceCleanupReason.TRUNCATED_ENTRY,
        AttendanceCleanupReason.SPEAKER_LINE,
        AttendanceCleanupReason.DECLINED_SEAT,
    }


def test_the_unscraped_members_are_not_in_the_colonial_file() -> None:
    colonial_keys = {(member.name, member.parliament_number) for member in _get_members("colonial_la_members.json")}
    unscraped_members = _get_members("unscraped_members.json")

    assert "Lee Li Lian" in {member.name for member in unscraped_members}
    assert not any((member.name, member.parliament_number) in colonial_keys for member in unscraped_members)


def test_every_speaker_role_falls_on_a_date_with_one_presiding_officer() -> None:
    for role in _get_file_cleanup().speaker_roles:
        day = parse_sitting_date(role.sitting_date).date()

        assert len([name for first, last, name in SPEAKER_TERMS if first <= day <= last]) == 1, role.sitting_date


def test_a_removal_is_planned_when_the_stored_row_matches_the_file() -> None:
    cleanup = AttendanceCleanup(removals=[_get_removal(1, "2.30 p.m", False)], corrections=[], speaker_roles=[])

    plan = build_attendance_cleanup_plan(cleanup, {1: _get_row(1, "2.30 p.m", False)}, {}, {}, {})

    assert plan.removal_id_to_reason == {1: AttendanceCleanupReason.NOT_A_NAME}
    assert plan.updates == []


@pytest.mark.parametrize(
    "stored_row",
    [
        None,
        _get_row(1, "Someone", True, sitting_id=2),
        _get_row(1, "Someone Else", True),
        _get_row(1, "Someone", False),
    ],
)
def test_a_removal_is_refused_when_the_stored_row_drifted(stored_row: Optional[Attendance]) -> None:
    cleanup = AttendanceCleanup(removals=[_get_removal(1)], corrections=[], speaker_roles=[])
    id_to_row = {} if stored_row is None else {1: stored_row}

    with pytest.raises(HansardWriteCheckError):
        build_attendance_cleanup_plan(cleanup, id_to_row, {}, {}, {})


def test_a_row_listed_twice_is_refused() -> None:
    cleanup = AttendanceCleanup(removals=[_get_removal(1)], corrections=[_get_correction(1)], speaker_roles=[])

    with pytest.raises(HansardWriteCheckError):
        build_attendance_cleanup_plan(cleanup, {1: _get_row(1)}, {}, {1: 5}, {})


def test_a_correction_renames_the_row_and_links_it() -> None:
    cleanup = AttendanceCleanup(removals=[], corrections=[_get_correction(1)], speaker_roles=[])
    stored_row = _get_row(1, "Wong Lm Ken", True, "Alexandra")

    plan = build_attendance_cleanup_plan(cleanup, {1: stored_row}, {}, {1: 5}, {})

    assert plan.updates == [AttendanceUpdate(1, "Wong Lin Ken", "Alexandra", 5, AttendanceCleanupReason.OCR_ALIAS)]


@pytest.mark.parametrize(
    ("stored_row", "id_to_speaker_id"),
    [
        (_get_row(1, "Wong Lm Ken", True, "Elsewhere"), {1: 5}),
        (_get_row(1, "Wong Lm Ken", True, "Alexandra", speaker_id=9), {1: 5}),
        (_get_row(1, "Wong Lm Ken", True, "Alexandra"), {}),
    ],
)
def test_a_correction_is_refused_when_the_row_drifted_or_the_name_has_no_speaker(stored_row: Attendance, id_to_speaker_id: dict[int, int]) -> None:
    cleanup = AttendanceCleanup(removals=[], corrections=[_get_correction(1)], speaker_roles=[])

    with pytest.raises(HansardWriteCheckError):
        build_attendance_cleanup_plan(cleanup, {1: stored_row}, {}, id_to_speaker_id, {})


def test_a_speaker_role_row_is_linked_to_the_presiding_officer_when_he_has_no_other_row() -> None:
    cleanup = AttendanceCleanup(removals=[], corrections=[], speaker_roles=[_get_role(1)])
    role_row = _get_row(1, "Speaker", True, "Sir George Oehlers, O.B.E.")
    other_row = _get_row(2, "Someone Else", True, speaker_id=8)

    plan = build_attendance_cleanup_plan(cleanup, {1: role_row}, {1: [role_row, other_row]}, {1: _HOLDER_ID}, {_HOLDER_ID: _HOLDER_NAME})

    assert plan.removal_id_to_reason == {}
    assert plan.updates == [AttendanceUpdate(1, _HOLDER_NAME, None, _HOLDER_ID, AttendanceCleanupReason.PRESIDING_OFFICER)]


def test_a_speaker_role_row_is_removed_when_the_presiding_officer_has_another_row() -> None:
    cleanup = AttendanceCleanup(removals=[], corrections=[], speaker_roles=[_get_role(1)])
    role_row = _get_row(1, "Speaker", True, "Sir George Oehlers, O.B.E.")
    holder_row = _get_row(2, _HOLDER_NAME, True, speaker_id=_HOLDER_ID)

    plan = build_attendance_cleanup_plan(cleanup, {1: role_row}, {1: [role_row, holder_row]}, {1: _HOLDER_ID}, {_HOLDER_ID: _HOLDER_NAME})

    assert plan.removal_id_to_reason == {1: AttendanceCleanupReason.REPEATED_ATTENDEE}
    assert plan.updates == []


def test_a_row_of_the_presiding_officer_that_is_itself_removed_does_not_count() -> None:
    cleanup = AttendanceCleanup(removals=[_get_removal(2, _HOLDER_NAME)], corrections=[], speaker_roles=[_get_role(1)])
    role_row = _get_row(1, "Speaker", True, "Sir George Oehlers, O.B.E.")
    holder_row = _get_row(2, _HOLDER_NAME, True, speaker_id=_HOLDER_ID)

    plan = build_attendance_cleanup_plan(cleanup, {1: role_row, 2: holder_row}, {1: [role_row, holder_row]}, {1: _HOLDER_ID}, {_HOLDER_ID: _HOLDER_NAME})

    assert plan.removal_id_to_reason == {2: AttendanceCleanupReason.NOT_A_NAME}
    assert [update.id for update in plan.updates] == [1]


def test_a_speaker_role_row_with_no_presiding_officer_is_refused() -> None:
    cleanup = AttendanceCleanup(removals=[], corrections=[], speaker_roles=[_get_role(1)])
    role_row = _get_row(1, "Speaker", True, "Sir George Oehlers, O.B.E.")

    with pytest.raises(HansardWriteCheckError):
        build_attendance_cleanup_plan(cleanup, {1: role_row}, {1: [role_row]}, {}, {})
