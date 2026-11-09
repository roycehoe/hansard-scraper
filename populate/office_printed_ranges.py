from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import Session

from crud.attendance_office import CRUDAttendanceOffice
from crud.office_printed_range import CRUDOfficePrintedRange
from crud.sitting import CRUDSitting, SittingDateRow
from database.office_printed_range import OfficePrintedRange
from exceptions import HansardWriteCheckError
from logs import logger
from services.office_printed_range import (
    build_office_printed_ranges,
    get_office_printed_range_changes,
)
from utils.sitting_dates import get_decade, parse_sitting_date


@dataclass(frozen=True)
class OfficePrintedRangePlan:
    office_printed_ranges: list[OfficePrintedRange]
    decade_to_row_count: Counter[int]
    rows_without_speaker_id: int


def _get_sorted_sitting_dates(session: Session) -> list[datetime]:
    return sorted(
        parse_sitting_date(sitting_date_row.sitting_date)
        for sitting_date_row in CRUDSitting(session).get_date_rows()
    )


def _get_late_sitting_dates(
    date_rows: list[SittingDateRow],
    sitting_ids: list[int],
    latest_stored_sitting_date: Optional[date],
) -> list[str]:
    if latest_stored_sitting_date is None:
        return []
    new_sitting_ids = set(sitting_ids)
    return [
        date_row.sitting_date
        for date_row in sorted(
            (date_row for date_row in date_rows if date_row.id in new_sitting_ids),
            key=lambda date_row: parse_sitting_date(date_row.sitting_date),
        )
        if parse_sitting_date(date_row.sitting_date).date() < latest_stored_sitting_date
    ]


def get_office_printed_range_plan(session: Session) -> OfficePrintedRangePlan:
    attendance_office_sitting_rows = CRUDAttendanceOffice(session).get_sitting_rows()
    office_printed_ranges = build_office_printed_ranges(
        attendance_office_sitting_rows,
        _get_sorted_sitting_dates(session),
        datetime.now(timezone.utc),
    )
    return OfficePrintedRangePlan(
        office_printed_ranges,
        Counter(
            get_decade(office_printed_range.first_sitting_date)
            for office_printed_range in office_printed_ranges
        ),
        sum(
            1
            for attendance_office_sitting_row in attendance_office_sitting_rows
            if attendance_office_sitting_row.speaker_id is None
        ),
    )


def _validate_can_commit_office_printed_ranges(
    session: Session, plan: OfficePrintedRangePlan
) -> None:
    stored_range_rows = CRUDOfficePrintedRange(session).get_rows_by_speaker_ids(
        sorted(
            {
                office_printed_range.speaker_id
                for office_printed_range in plan.office_printed_ranges
            }
        )
    )
    if len(stored_range_rows) != len(plan.office_printed_ranges):
        raise HansardWriteCheckError(
            f"Stored {len(stored_range_rows)} office printed ranges, the plan has {len(plan.office_printed_ranges)}"
        )
    stored_decade_to_row_count = Counter(
        get_decade(stored_range_row.first_sitting_date)
        for stored_range_row in stored_range_rows
    )
    if stored_decade_to_row_count != plan.decade_to_row_count:
        raise HansardWriteCheckError(
            f"Stored office printed ranges by decade {dict(stored_decade_to_row_count)}, the plan has {dict(plan.decade_to_row_count)}"
        )
    stored_sitting_count = sum(
        stored_range_row.sitting_count for stored_range_row in stored_range_rows
    )
    planned_sitting_count = sum(
        office_printed_range.sitting_count
        for office_printed_range in plan.office_printed_ranges
    )
    if stored_sitting_count != planned_sitting_count:
        raise HansardWriteCheckError(
            f"Stored office printed ranges cover {stored_sitting_count} sittings, the plan covers {planned_sitting_count}"
        )


def write_office_printed_range_plan(
    session: Session, plan: OfficePrintedRangePlan
) -> None:
    CRUDOfficePrintedRange(session).add_many(plan.office_printed_ranges)
    _validate_can_commit_office_printed_ranges(session, plan)


# NOTE: inserts and extends only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_office_printed_ranges(
    session: Session, sitting_ids: list[int]
) -> list[str]:
    date_rows = CRUDSitting(session).get_date_rows()
    latest_stored_sitting_date = CRUDAttendanceOffice(
        session
    ).get_max_sitting_date_by_sitting_ids_not_in(sitting_ids)
    late_sitting_dates = _get_late_sitting_dates(
        date_rows, sitting_ids, latest_stored_sitting_date
    )
    if late_sitting_dates:
        logger.info(
            f"Office printed ranges: {len(late_sitting_dates)} sittings are earlier than the latest stored sitting, so no range was written"
        )
        return late_sitting_dates
    attendance_office_sitting_rows = CRUDAttendanceOffice(
        session
    ).get_sitting_rows_by_sitting_ids(sitting_ids)
    office_printed_range_rows = CRUDOfficePrintedRange(session).get_rows_by_speaker_ids(
        sorted(
            {
                attendance_office_sitting_row.speaker_id
                for attendance_office_sitting_row in attendance_office_sitting_rows
                if attendance_office_sitting_row.speaker_id is not None
            }
        )
    )
    office_printed_range_changes = get_office_printed_range_changes(
        attendance_office_sitting_rows,
        office_printed_range_rows,
        _get_sorted_sitting_dates(session),
        datetime.now(timezone.utc),
    )
    CRUDOfficePrintedRange(session).add_many(
        office_printed_range_changes.office_printed_ranges
    )
    CRUDOfficePrintedRange(session).update_many(
        office_printed_range_changes.office_printed_range_updates
    )
    logger.info(
        f"Office printed ranges: added {len(office_printed_range_changes.office_printed_ranges)}, extended {len(office_printed_range_changes.office_printed_range_updates)}"
    )
    return []
