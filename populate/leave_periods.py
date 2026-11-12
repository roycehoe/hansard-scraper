from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.leave_period import CRUDLeavePeriod
from crud.leave_period_printing import CRUDLeavePeriodPrinting
from crud.sitting import CRUDSitting, SittingAttendanceTextRow, SittingLeaveTextRow
from crud.speaker import CRUDSpeaker
from database.leave_period import LeavePeriod, LeavePeriodPrinting
from enums import LeaveOfficeSource
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.leave_date_misprint import LeaveDateMisprint
from schemas.leave_heading_year import LeaveHeadingYear
from services.attendance import (
    build_speaker_lookups,
    get_sitting_entry_names,
    get_sitting_entry_offices,
)
from services.leave_period import (
    LeaveEntrySpeakerLink,
    build_leave_entries_from_list,
    get_leave_entry_speaker_link,
)
from services.leave_section import build_leave_entries_from_markdown
from utils.data_files import get_leave_date_misprints, get_leave_heading_years
from utils.leave_entry import (
    LeaveEntry,
    get_leave_name_key,
    get_leave_period_key,
    is_covering_sitting,
)
from utils.parliament_numbers import infer_parliament
from utils.sitting_dates import parse_sitting_date
from utils.speaker_resolution import SpeakerLookups

_SITTING_BATCH = 20


@dataclass(frozen=True)
class LeaveOffice:
    office_printed: str
    office_source: LeaveOfficeSource


@dataclass(frozen=True)
class PlannedLeavePrinting:
    sitting_id: int
    sitting_date: date
    period_key: str
    leave_entry: LeaveEntry
    speaker_link: Optional[LeaveEntrySpeakerLink]
    is_covering_sitting: Optional[bool]
    leave_office: Optional[LeaveOffice]


def _get_attendance_text_row(
    sitting_leave_text_row: SittingLeaveTextRow,
) -> SittingAttendanceTextRow:
    return SittingAttendanceTextRow(
        sitting_leave_text_row.id,
        sitting_leave_text_row.sitting_date,
        sitting_leave_text_row.parlement_no,
        sitting_leave_text_row.volume_no,
        sitting_leave_text_row.markdown_content,
        sitting_leave_text_row.attendance_list,
    )


def _get_leave_entries(
    sitting_leave_text_row: SittingLeaveTextRow,
    sitting_date: date,
    leave_date_misprints: list[LeaveDateMisprint],
    leave_heading_years: list[LeaveHeadingYear],
) -> list[LeaveEntry]:
    if sitting_leave_text_row.markdown_content is not None:
        return build_leave_entries_from_markdown(
            sitting_leave_text_row.markdown_content,
            sitting_date,
            leave_date_misprints,
            leave_heading_years,
        )
    if sitting_leave_text_row.ptba_list is None:
        return []
    return build_leave_entries_from_list(
        sitting_leave_text_row.ptba_list,
        sitting_leave_text_row.ptba_from,
        sitting_leave_text_row.ptba_to,
        sitting_date,
    )


def _get_entry_name_key_to_speaker_ids(
    sitting_leave_text_row: SittingLeaveTextRow,
    lookups: SpeakerLookups,
    speaker_name_to_speaker_id: dict[Optional[str], int],
) -> dict[str, list[Optional[int]]]:
    entry_name_key_to_speaker_ids: dict[str, list[Optional[int]]] = {}
    for entry_name in get_sitting_entry_names(
        _get_attendance_text_row(sitting_leave_text_row), lookups
    ):
        entry_name_key_to_speaker_ids.setdefault(
            get_leave_name_key(entry_name.printed_name), []
        ).append(speaker_name_to_speaker_id.get(entry_name.speaker_name))
    return entry_name_key_to_speaker_ids


def _get_speaker_id_to_office_printed(
    sitting_leave_text_row: SittingLeaveTextRow,
    lookups: SpeakerLookups,
    speaker_name_to_speaker_id: dict[Optional[str], int],
) -> dict[int, str]:
    speaker_id_to_office_printed: dict[int, str] = {}
    for entry_office in get_sitting_entry_offices(
        _get_attendance_text_row(sitting_leave_text_row), lookups
    ):
        speaker_id = speaker_name_to_speaker_id.get(entry_office.speaker_name)
        if speaker_id is None:
            continue
        speaker_id_to_office_printed.setdefault(speaker_id, entry_office.office_printed)
    return speaker_id_to_office_printed


def _get_leave_office(
    leave_entry: LeaveEntry, attendance_office_printed: Optional[str]
) -> Optional[LeaveOffice]:
    if leave_entry.office_printed is not None:
        return LeaveOffice(
            leave_entry.office_printed, LeaveOfficeSource.PRINTED_ON_ENTRY
        )
    if attendance_office_printed is None:
        return None
    return LeaveOffice(attendance_office_printed, LeaveOfficeSource.ATTENDANCE_LIST)


def _get_sitting_printings(
    sitting_leave_text_row: SittingLeaveTextRow,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
    speaker_name_to_speaker_id: dict[Optional[str], int],
    leave_date_misprints: list[LeaveDateMisprint],
    leave_heading_years: list[LeaveHeadingYear],
) -> list[PlannedLeavePrinting]:
    sitting_date = parse_sitting_date(sitting_leave_text_row.sitting_date).date()
    leave_entries = _get_leave_entries(
        sitting_leave_text_row,
        sitting_date,
        leave_date_misprints,
        leave_heading_years,
    )
    if not leave_entries:
        return []
    entry_name_key_to_speaker_ids = _get_entry_name_key_to_speaker_ids(
        sitting_leave_text_row, lookups, speaker_name_to_speaker_id
    )
    speaker_id_to_office_printed = _get_speaker_id_to_office_printed(
        sitting_leave_text_row, lookups, speaker_name_to_speaker_id
    )
    parliament_number = infer_parliament(
        sitting_leave_text_row.parlement_no, sitting_leave_text_row.volume_no
    )
    planned_printings = []
    for leave_entry in leave_entries:
        name = leave_entry.printed_name or leave_entry.carried_name
        speaker_link = (
            None
            if name is None
            else get_leave_entry_speaker_link(
                name,
                parliament_number,
                lookups,
                name_parliament_number_to_speaker_id,
                entry_name_key_to_speaker_ids,
            )
        )
        leave_dates = leave_entry.leave_dates
        start_date = None if leave_dates is None else leave_dates.start_date
        end_date = None if leave_dates is None else leave_dates.end_date
        attendance_office_printed = (
            None
            if speaker_link is None
            else speaker_id_to_office_printed.get(speaker_link.speaker_id)
        )
        planned_printings.append(
            PlannedLeavePrinting(
                sitting_id=sitting_leave_text_row.id,
                sitting_date=sitting_date,
                period_key=get_leave_period_key(
                    name,
                    start_date,
                    end_date,
                    sitting_leave_text_row.id,
                    leave_entry.ordinal,
                ),
                leave_entry=leave_entry,
                speaker_link=speaker_link,
                is_covering_sitting=is_covering_sitting(
                    start_date, end_date, sitting_date
                ),
                leave_office=_get_leave_office(leave_entry, attendance_office_printed),
            )
        )
    return planned_printings


def get_leave_period_plan(
    session: Session, sitting_ids: list[int]
) -> list[PlannedLeavePrinting]:
    speakers = CRUDSpeaker(session).get_all()
    name_parliament_number_to_speaker_id = {
        (speaker.name, speaker.parliament_number): speaker.id
        for speaker in speakers
        if speaker.id is not None
    }
    lookups = build_speaker_lookups(speakers)
    leave_date_misprints = get_leave_date_misprints()
    leave_heading_years = get_leave_heading_years()
    planned_printings = []
    sorted_sitting_ids = sorted(sitting_ids)
    for start in range(0, len(sorted_sitting_ids), _SITTING_BATCH):
        batch_sitting_ids = sorted_sitting_ids[start : start + _SITTING_BATCH]
        sitting_id_to_speaker_name_to_speaker_id: defaultdict[
            int, dict[Optional[str], int]
        ] = defaultdict(dict)
        for attendance_name_row in CRUDAttendance(
            session
        ).get_name_rows_by_sitting_ids_and_speaker_id_not_null(batch_sitting_ids):
            sitting_id_to_speaker_name_to_speaker_id[attendance_name_row.sitting_id][
                attendance_name_row.speaker_name
            ] = attendance_name_row.speaker_id
        for sitting_leave_text_row in CRUDSitting(session).get_leave_text_rows_by_ids(
            batch_sitting_ids
        ):
            planned_printings.extend(
                _get_sitting_printings(
                    sitting_leave_text_row,
                    lookups,
                    name_parliament_number_to_speaker_id,
                    sitting_id_to_speaker_name_to_speaker_id[sitting_leave_text_row.id],
                    leave_date_misprints,
                    leave_heading_years,
                )
            )
    return sorted(
        planned_printings,
        key=lambda planned_printing: (
            planned_printing.sitting_date,
            planned_printing.sitting_id,
            planned_printing.leave_entry.ordinal,
        ),
    )


def _insert_leave_period_plan(
    session: Session, planned_printings: list[PlannedLeavePrinting]
) -> None:
    period_key_to_first_printing: dict[str, PlannedLeavePrinting] = {}
    for planned_printing in planned_printings:
        period_key_to_first_printing.setdefault(
            planned_printing.period_key, planned_printing
        )
    period_key_to_id = {
        leave_period.period_key: leave_period.id
        for leave_period in CRUDLeavePeriod(session).get_by_period_keys(
            list(period_key_to_first_printing)
        )
        if leave_period.id is not None
    }
    new_leave_periods = []
    for period_key, first_printing in period_key_to_first_printing.items():
        if period_key in period_key_to_id:
            continue
        leave_entry = first_printing.leave_entry
        leave_dates = leave_entry.leave_dates
        new_leave_periods.append(
            LeavePeriod(
                period_key=period_key,
                name=leave_entry.printed_name or leave_entry.carried_name,
                start_date=None if leave_dates is None else leave_dates.start_date,
                end_date=None if leave_dates is None else leave_dates.end_date,
                end_text=leave_entry.end_text,
            )
        )
    CRUDLeavePeriod(session).add_many(new_leave_periods)
    for new_leave_period in new_leave_periods:
        if new_leave_period.id is not None:
            period_key_to_id[new_leave_period.period_key] = new_leave_period.id
    CRUDLeavePeriodPrinting(session).add_many(
        [
            LeavePeriodPrinting(
                ordinal=planned_printing.leave_entry.ordinal,
                sitting_date=planned_printing.sitting_date,
                printed_name=planned_printing.leave_entry.printed_name,
                carried_name=planned_printing.leave_entry.carried_name,
                printed_from=planned_printing.leave_entry.printed_from,
                printed_to=planned_printing.leave_entry.printed_to,
                printed_line=planned_printing.leave_entry.printed_line,
                printed_heading_from=planned_printing.leave_entry.printed_heading_from,
                printed_heading_to=planned_printing.leave_entry.printed_heading_to,
                office_printed=(
                    None
                    if planned_printing.leave_office is None
                    else planned_printing.leave_office.office_printed
                ),
                entry_format=planned_printing.leave_entry.entry_format,
                name_source=planned_printing.leave_entry.name_source,
                year_source=planned_printing.leave_entry.year_source,
                office_source=(
                    None
                    if planned_printing.leave_office is None
                    else planned_printing.leave_office.office_source
                ),
                speaker_link_source=(
                    None
                    if planned_printing.speaker_link is None
                    else planned_printing.speaker_link.speaker_link_source
                ),
                is_covering_sitting=planned_printing.is_covering_sitting,
                sitting_id=planned_printing.sitting_id,
                leave_period_id=period_key_to_id[planned_printing.period_key],
                speaker_id=(
                    None
                    if planned_printing.speaker_link is None
                    else planned_printing.speaker_link.speaker_id
                ),
            )
            for planned_printing in planned_printings
        ]
    )


def _validate_can_commit_leave_periods(
    session: Session, planned_printings: list[PlannedLeavePrinting]
) -> None:
    stored_format_counts = Counter(
        {
            (count.entry_format, count.name_source, count.year_source): (
                count.printing_count
            )
            for count in CRUDLeavePeriodPrinting(
                session
            ).get_entry_format_and_name_source_and_year_source_counts()
        }
    )
    planned_format_counts = Counter(
        (
            planned_printing.leave_entry.entry_format,
            planned_printing.leave_entry.name_source,
            planned_printing.leave_entry.year_source,
        )
        for planned_printing in planned_printings
    )
    if stored_format_counts != planned_format_counts:
        raise HansardWriteCheckError(
            f"Stored leave period printings by format, name source and year source {dict(stored_format_counts)}, the plan has {dict(planned_format_counts)}"
        )
    stored_period_count = CRUDLeavePeriod(session).get_count()
    planned_period_count = len(
        {planned_printing.period_key for planned_printing in planned_printings}
    )
    if stored_period_count != planned_period_count:
        raise HansardWriteCheckError(
            f"{stored_period_count} leave periods are stored, the plan has {planned_period_count}"
        )


def write_leave_period_plan(
    session: Session, planned_printings: list[PlannedLeavePrinting]
) -> None:
    CRUDLeavePeriodPrinting(session).delete_all()
    CRUDLeavePeriod(session).delete_all()
    _insert_leave_period_plan(session, planned_printings)
    _validate_can_commit_leave_periods(session, planned_printings)


# NOTE: inserts only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_leave_periods(session: Session, sitting_ids: list[int]) -> None:
    planned_printings = get_leave_period_plan(session, sitting_ids)
    _insert_leave_period_plan(session, planned_printings)
    logger.info(
        f"Leave periods: added {len(planned_printings)} printings for {len(sitting_ids)} sittings"
    )
