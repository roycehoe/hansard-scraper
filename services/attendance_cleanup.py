from dataclasses import dataclass
from typing import Optional

from database.attendance import Attendance
from enums import AttendanceCleanupReason
from exceptions import HansardWriteCheckError
from schemas.attendance_cleanup import AttendanceCleanup, AttendanceRowKey


@dataclass(frozen=True)
class AttendanceUpdate:
    id: int
    speaker_name: str
    location_name: Optional[str]
    speaker_id: int
    reason: AttendanceCleanupReason


@dataclass(frozen=True)
class AttendanceCleanupPlan:
    removal_id_to_reason: dict[int, AttendanceCleanupReason]
    updates: list[AttendanceUpdate]


def _validate_can_clean_row(attendance_id_to_attendance: dict[int, Attendance], expected: AttendanceRowKey) -> None:
    row = attendance_id_to_attendance.get(expected.id)
    if row is None:
        raise HansardWriteCheckError(f"Attendance row {expected.id} is not stored")
    if row.sitting_id != expected.sitting_id:
        raise HansardWriteCheckError(f"Attendance row {expected.id}: sitting {row.sitting_id}, expected {expected.sitting_id}")
    if row.speaker_name != expected.speaker_name:
        raise HansardWriteCheckError(f"Attendance row {expected.id}: name {row.speaker_name!r}, expected {expected.speaker_name!r}")
    if row.is_present != expected.is_present:
        raise HansardWriteCheckError(f"Attendance row {expected.id}: presence {row.is_present}, expected {expected.is_present}")


def _validate_can_link_row(attendance_id_to_attendance: dict[int, Attendance], expected: AttendanceRowKey, location_name: Optional[str]) -> None:
    _validate_can_clean_row(attendance_id_to_attendance, expected)
    row = attendance_id_to_attendance[expected.id]
    if row.location_name != location_name:
        raise HansardWriteCheckError(f"Attendance row {expected.id}: location {row.location_name!r}, expected {location_name!r}")
    if row.speaker_id is not None:
        raise HansardWriteCheckError(f"Attendance row {expected.id}: already linked to speaker {row.speaker_id}")


def build_attendance_cleanup_plan(
    cleanup: AttendanceCleanup,
    attendance_id_to_attendance: dict[int, Attendance],
    sitting_id_to_rows: dict[int, list[Attendance]],
    attendance_id_to_speaker_id: dict[int, int],
    speaker_id_to_name: dict[int, str],
) -> AttendanceCleanupPlan:
    entry_ids = [entry.id for entry in (*cleanup.removals, *cleanup.corrections, *cleanup.speaker_roles)]
    if len(set(entry_ids)) != len(entry_ids):
        raise HansardWriteCheckError("An attendance row appears twice in the cleanup file")

    removal_id_to_reason: dict[int, AttendanceCleanupReason] = {}
    for removal in cleanup.removals:
        _validate_can_clean_row(attendance_id_to_attendance, removal)
        removal_id_to_reason[removal.id] = removal.reason

    updates = []
    for correction in cleanup.corrections:
        _validate_can_link_row(attendance_id_to_attendance, correction, correction.location_name)
        if correction.id not in attendance_id_to_speaker_id:
            raise HansardWriteCheckError(f"Attendance row {correction.id}: no speaker row for {correction.speaker_name_after!r}")
        updates.append(
            AttendanceUpdate(
                correction.id, correction.speaker_name_after, correction.location_name_after, attendance_id_to_speaker_id[correction.id], correction.reason
            )
        )

    for role in cleanup.speaker_roles:
        _validate_can_link_row(attendance_id_to_attendance, role, role.location_name)
        if role.id not in attendance_id_to_speaker_id:
            raise HansardWriteCheckError(f"Attendance row {role.id}: no presiding officer for {role.sitting_date}")
        holder_id = attendance_id_to_speaker_id[role.id]
        is_holder_repeated = any(
            other.id != role.id and other.id not in removal_id_to_reason and other.speaker_id == holder_id
            for other in sitting_id_to_rows[role.sitting_id]
        )
        if is_holder_repeated:
            removal_id_to_reason[role.id] = AttendanceCleanupReason.REPEATED_ATTENDEE
            continue
        updates.append(AttendanceUpdate(role.id, speaker_id_to_name[holder_id], None, holder_id, AttendanceCleanupReason.PRESIDING_OFFICER))

    return AttendanceCleanupPlan(removal_id_to_reason, updates)
