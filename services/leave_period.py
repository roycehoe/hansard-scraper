import json
import re
from datetime import date
from typing import Optional

from enums import LeaveEntryFormat, LeaveNameSource, LeaveYearSource
from schemas.hansard_report_response import HansardReportPermissionEntry
from utils.leave_entry import (
    MONTH_NAME_TO_NUMBER,
    DayAndMonth,
    LeaveDates,
    LeaveEntry,
    get_candidate_years,
    get_nearest_year_dates,
)

_PRINTED_DAY_AND_MONTH_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\.?$")


def _get_stored_text(printed_text: Optional[str]) -> Optional[str]:
    if printed_text is None:
        return None
    if not printed_text.strip():
        return None
    return printed_text


def _get_day_and_month(printed_date: Optional[str]) -> Optional[DayAndMonth]:
    if printed_date is None:
        return None
    match = _PRINTED_DAY_AND_MONTH_RE.match(printed_date.strip())
    if match is None:
        return None
    month = MONTH_NAME_TO_NUMBER.get(match.group(2).lower())
    if month is None:
        return None
    return DayAndMonth(int(match.group(1)), month)


def _get_list_entry_dates(
    permission_entry: HansardReportPermissionEntry, sitting_date: date
) -> Optional[LeaveDates]:
    printed_start = _get_day_and_month(permission_entry.printed_from)
    if printed_start is None:
        return None
    if permission_entry.end_dt_flag is True:
        return get_nearest_year_dates(
            printed_start, None, sitting_date, get_candidate_years(sitting_date)
        )
    printed_end = _get_day_and_month(permission_entry.printed_to)
    if printed_end is None:
        return None
    return get_nearest_year_dates(
        printed_start, printed_end, sitting_date, get_candidate_years(sitting_date)
    )


def build_leave_entries_from_list(
    permission_list: str,
    heading_from: Optional[str],
    heading_to: Optional[str],
    sitting_date: date,
) -> list[LeaveEntry]:
    leave_entries = []
    last_printed_name: Optional[str] = None
    for ordinal, raw_entry in enumerate(json.loads(permission_list), start=1):
        permission_entry = HansardReportPermissionEntry.model_validate(raw_entry)
        printed_name = _get_stored_text(permission_entry.mp_name)
        carried_name = None if printed_name is not None else last_printed_name
        if printed_name is not None:
            name_source = LeaveNameSource.PRINTED
        elif carried_name is not None:
            name_source = LeaveNameSource.CARRIED_FROM_ROW_ABOVE
        else:
            name_source = LeaveNameSource.NONE
        leave_dates = _get_list_entry_dates(permission_entry, sitting_date)
        leave_entries.append(
            LeaveEntry(
                ordinal=ordinal,
                printed_name=printed_name,
                carried_name=carried_name,
                printed_from=_get_stored_text(permission_entry.printed_from),
                printed_to=_get_stored_text(permission_entry.printed_to),
                printed_line=None,
                printed_heading_from=_get_stored_text(heading_from),
                printed_heading_to=_get_stored_text(heading_to),
                office_printed=None,
                leave_dates=leave_dates,
                end_text=(
                    _get_stored_text(permission_entry.end_dt_text)
                    if permission_entry.end_dt_flag is True
                    else None
                ),
                entry_format=LeaveEntryFormat.STRUCTURED_LIST,
                name_source=name_source,
                year_source=(
                    None if leave_dates is None else LeaveYearSource.NEAREST_TO_SITTING
                ),
            )
        )
        if printed_name is not None:
            last_printed_name = printed_name
    return leave_entries
