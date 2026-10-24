from typing import Optional

import pytest

from database.attendance import Attendance
from exceptions import HansardWriteCheckError
from services.attendance import AttendanceNameChange, get_attendance_name_changes

_SITTING_ID = 1


def _get_row(attendance_id: int, speaker_name: str, is_present: bool = True, location_name: Optional[str] = None, speaker_id: Optional[int] = None) -> Attendance:
    return Attendance(id=attendance_id, sitting_id=_SITTING_ID, speaker_name=speaker_name, is_present=is_present, location_name=location_name, speaker_id=speaker_id)


def test_name_changes_cover_the_rows_whose_name_differs_and_are_empty_once_applied() -> None:
    stored_rows = [_get_row(1, "Lee Kuan Yew", location_name="Tanjong Pagar", speaker_id=5), _get_row(2, "Goh Keng Swee  ", speaker_id=6)]
    built_rows = [_get_row(0, "Lee Kuan Yew", location_name="Tanjong Pagar"), _get_row(0, "Goh Keng Swee")]

    name_changes = get_attendance_name_changes(_SITTING_ID, stored_rows, built_rows)

    assert name_changes == [AttendanceNameChange(2, _SITTING_ID, "Goh Keng Swee  ", "Goh Keng Swee", True, None, 6)]
    applied_rows = [_get_row(1, "Lee Kuan Yew", location_name="Tanjong Pagar", speaker_id=5), _get_row(2, "Goh Keng Swee", speaker_id=6)]
    assert get_attendance_name_changes(_SITTING_ID, applied_rows, built_rows) == []


def test_rows_equal_to_a_built_row_are_paired_first_and_the_rest_by_position() -> None:
    stored_rows = [_get_row(1, "Lee Kuan Yew", speaker_id=5), _get_row(2, "Goh Keng Swee  ", speaker_id=6), _get_row(3, "Toh Chin Chye", speaker_id=7)]
    built_rows = [_get_row(0, "Lee Kuan Yew"), _get_row(0, "Toh Chin Chye"), _get_row(0, "Goh Keng Swee")]

    name_changes = get_attendance_name_changes(_SITTING_ID, stored_rows, built_rows)

    assert name_changes == [AttendanceNameChange(2, _SITTING_ID, "Goh Keng Swee  ", "Goh Keng Swee", True, None, 6)]


@pytest.mark.parametrize(
    "built_rows",
    [
        [_get_row(0, "Lee Kuan Yew")],
        [_get_row(0, "Lee Kuan Yew", is_present=False), _get_row(0, "Goh Keng Swee")],
        [_get_row(0, "Lee Kuan Yew", location_name="Tanjong Pagar"), _get_row(0, "Goh Keng Swee")],
    ],
)
def test_a_sitting_is_refused_when_stage_7_differs_in_more_than_a_name(built_rows: list[Attendance]) -> None:
    stored_rows = [_get_row(1, "Lee Kuan Yew"), _get_row(2, "Goh Keng Swee")]

    with pytest.raises(HansardWriteCheckError):
        get_attendance_name_changes(_SITTING_ID, stored_rows, built_rows)
