from typing import Optional

import pytest

from database.attendance import Attendance
from exceptions import HansardWriteCheckError
from schemas.attendance_completion_plan import (
    AttendanceCompletionPlan,
    PlannedAttendance,
    SittingAttendanceCompletion,
)
from scripts.complete_truncated_attendance import (
    get_rows_to_insert,
    validate_can_plan_speaker_ids,
)

_SITTING_ID = 6460


def _get_row(speaker_name: str, is_present: bool = True, location_name: Optional[str] = "Aljunied", speaker_id: Optional[int] = None) -> Attendance:
    return Attendance(sitting_id=_SITTING_ID, speaker_name=speaker_name, is_present=is_present, location_name=location_name, speaker_id=speaker_id)


def _get_planned_row(speaker_id: Optional[int]) -> PlannedAttendance:
    return PlannedAttendance(speaker_name="Someone", is_present=True, location_name="Aljunied", speaker_id=speaker_id)


def test_rows_to_insert_are_the_built_rows_no_stored_row_matches() -> None:
    stored_rows = [_get_row("A"), _get_row("C")]
    built_rows = [_get_row("A"), _get_row("B"), _get_row("C"), _get_row("D", is_present=False)]

    rows_to_insert = get_rows_to_insert(_SITTING_ID, stored_rows, built_rows)

    assert [row_to_insert.speaker_name for row_to_insert in rows_to_insert] == ["B", "D"]


def test_a_repeated_built_row_is_matched_once_per_stored_row() -> None:
    stored_rows = [_get_row("A")]
    built_rows = [_get_row("A"), _get_row("A")]

    rows_to_insert = get_rows_to_insert(_SITTING_ID, stored_rows, built_rows)

    assert [row_to_insert.speaker_name for row_to_insert in rows_to_insert] == ["A"]


def test_a_stored_row_stage_7_does_not_build_refuses_the_sitting() -> None:
    stored_rows = [_get_row("A"), _get_row("Old Spelling")]
    built_rows = [_get_row("A"), _get_row("B"), _get_row("C")]

    with pytest.raises(HansardWriteCheckError, match="1 stored rows are not built"):
        get_rows_to_insert(_SITTING_ID, stored_rows, built_rows)


def test_a_stored_row_with_another_presence_or_location_is_not_matched() -> None:
    stored_rows = [_get_row("A", is_present=False)]
    built_rows = [_get_row("A"), _get_row("B")]

    with pytest.raises(HansardWriteCheckError):
        get_rows_to_insert(_SITTING_ID, stored_rows, built_rows)


def test_a_planned_speaker_already_in_the_sitting_is_refused() -> None:
    stored_rows = [_get_row("A", speaker_id=5)]

    with pytest.raises(HansardWriteCheckError, match="repeats a speaker"):
        validate_can_plan_speaker_ids(_SITTING_ID, stored_rows, [_get_planned_row(5)])


def test_two_planned_rows_of_one_speaker_are_refused() -> None:
    with pytest.raises(HansardWriteCheckError, match="repeats a speaker"):
        validate_can_plan_speaker_ids(_SITTING_ID, [], [_get_planned_row(7), _get_planned_row(7)])


def test_unlinked_planned_rows_do_not_count_as_repeats() -> None:
    validate_can_plan_speaker_ids(_SITTING_ID, [_get_row("A")], [_get_planned_row(None), _get_planned_row(None)])


def test_the_plan_file_reads_back_to_an_equal_plan() -> None:
    plan = AttendanceCompletionPlan(sittings=[
        SittingAttendanceCompletion(
            sitting_id=_SITTING_ID, sitting_date="18-3-1986", markdown_md5="0" * 32,
            stored_row_count=46, built_row_count=79, rows_to_insert=[_get_planned_row(3), _get_planned_row(None)],
        )
    ])

    assert AttendanceCompletionPlan.model_validate_json(plan.model_dump_json()) == plan
