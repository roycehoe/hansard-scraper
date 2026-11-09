from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.attendance_office import CRUDAttendanceOffice
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from database.attendance_office import AttendanceOffice
from enums import AttendanceOfficeSource
from exceptions import HansardWriteCheckError
from logs import logger
from services.attendance import build_speaker_lookups, get_sitting_attendance_offices
from utils.office import get_office_class
from utils.sitting_dates import get_decade, parse_sitting_date

_SITTING_BATCH = 20


@dataclass(frozen=True)
class AttendanceOfficePlan:
    sitting_ids: list[int]
    attendance_offices: list[AttendanceOffice]
    decade_to_row_count: Counter[int]
    source_to_row_count: Counter[AttendanceOfficeSource]
    entries_without_attendance_row: int
    duplicate_entries: int


def get_attendance_office_plan(
    session: Session, sitting_ids: list[int]
) -> AttendanceOfficePlan:
    extracted_at = datetime.now(timezone.utc)
    lookups = build_speaker_lookups(CRUDSpeaker(session).get_all())
    attendance_offices: list[AttendanceOffice] = []
    decade_to_row_count: Counter[int] = Counter()
    source_to_row_count: Counter[AttendanceOfficeSource] = Counter()
    entries_without_attendance_row = 0
    duplicate_entries = 0
    for start in range(0, len(sitting_ids), _SITTING_BATCH):
        batch_sitting_ids = sitting_ids[start : start + _SITTING_BATCH]
        sitting_attendance_text_rows = CRUDSitting(
            session
        ).get_attendance_text_rows_by_ids(batch_sitting_ids)
        sitting_id_and_speaker_name_to_attendance_id = {
            (attendance_id_name_row.sitting_id, attendance_id_name_row.speaker_name): (
                attendance_id_name_row.id
            )
            for attendance_id_name_row in CRUDAttendance(
                session
            ).get_id_name_rows_by_sitting_ids(batch_sitting_ids)
        }
        for sitting_attendance_text_row in sitting_attendance_text_rows:
            decade = get_decade(
                parse_sitting_date(sitting_attendance_text_row.sitting_date)
            )
            taken_attendance_ids: set[int] = set()
            for sitting_attendance_office in get_sitting_attendance_offices(
                sitting_attendance_text_row, lookups
            ):
                attendance_id = sitting_id_and_speaker_name_to_attendance_id.get(
                    (
                        sitting_attendance_text_row.id,
                        sitting_attendance_office.speaker_name,
                    )
                )
                if attendance_id is None:
                    entries_without_attendance_row += 1
                    continue
                if attendance_id in taken_attendance_ids:
                    duplicate_entries += 1
                    continue
                taken_attendance_ids.add(attendance_id)
                attendance_offices.append(
                    AttendanceOffice(
                        office_printed=sitting_attendance_office.office_printed,
                        entry_line_printed=sitting_attendance_office.entry_line_printed,
                        office_class=get_office_class(
                            sitting_attendance_office.office_printed
                        ),
                        source=sitting_attendance_office.source,
                        extracted_at=extracted_at,
                        attendance_id=attendance_id,
                    )
                )
                decade_to_row_count[decade] += 1
                source_to_row_count[sitting_attendance_office.source] += 1
    return AttendanceOfficePlan(
        sitting_ids,
        attendance_offices,
        decade_to_row_count,
        source_to_row_count,
        entries_without_attendance_row,
        duplicate_entries,
    )


def _validate_can_commit_attendance_offices(
    session: Session, plan: AttendanceOfficePlan
) -> None:
    stored_decade_to_row_count = Counter(
        get_decade(parse_sitting_date(attendance_office_sitting_row.sitting_date))
        for attendance_office_sitting_row in CRUDAttendanceOffice(
            session
        ).get_sitting_rows_by_sitting_ids(plan.sitting_ids)
    )
    if stored_decade_to_row_count != plan.decade_to_row_count:
        raise HansardWriteCheckError(
            f"Stored attendance offices by decade {dict(stored_decade_to_row_count)}, the plan has {dict(plan.decade_to_row_count)}"
        )


def _insert_attendance_offices(session: Session, plan: AttendanceOfficePlan) -> None:
    CRUDAttendanceOffice(session).add_many(plan.attendance_offices)
    _validate_can_commit_attendance_offices(session, plan)


def write_attendance_office_plan(session: Session, plan: AttendanceOfficePlan) -> None:
    for start in range(0, len(plan.sitting_ids), _SITTING_BATCH):
        batch_sitting_ids = plan.sitting_ids[start : start + _SITTING_BATCH]
        stored_attendance_office_count = len(
            CRUDAttendanceOffice(session).get_sitting_rows_by_sitting_ids(
                batch_sitting_ids
            )
        )
        deleted_attendance_office_count = CRUDAttendanceOffice(
            session
        ).delete_by_sitting_ids(batch_sitting_ids)
        if deleted_attendance_office_count != stored_attendance_office_count:
            raise HansardWriteCheckError(
                f"Deleted {deleted_attendance_office_count} attendance offices, read {stored_attendance_office_count}"
            )
    _insert_attendance_offices(session, plan)


# NOTE: inserts only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_attendance_offices(session: Session, sitting_ids: list[int]) -> None:
    plan = get_attendance_office_plan(session, sitting_ids)
    _insert_attendance_offices(session, plan)
    logger.info(
        f"Attendance offices: added {len(plan.attendance_offices)} rows for {len(plan.sitting_ids)} sittings"
    )
