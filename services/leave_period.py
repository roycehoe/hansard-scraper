import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from enums import (
    LeaveEntryFormat,
    LeaveNameSource,
    LeaveSpeakerLinkSource,
    LeaveYearSource,
)
from schemas.hansard_report_response import HansardReportPermissionEntry
from utils.leave_entry import (
    MONTH_NAME_TO_NUMBER,
    DayAndMonth,
    LeaveDates,
    LeaveEntry,
    get_candidate_years,
    get_leave_name_key,
    get_nearest_year_dates,
    get_open_period_candidate_years,
)
from utils.names import normalize_name, period_normalize, strip_title
from utils.speaker_resolution import SpeakerLookups

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
            printed_start,
            None,
            sitting_date,
            get_open_period_candidate_years(printed_start, sitting_date),
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


@dataclass(frozen=True)
class LeaveEntrySpeakerLink:
    speaker_id: int
    speaker_link_source: LeaveSpeakerLinkSource


def get_leave_entry_speaker_link(
    name: str,
    parliament_number: Optional[int],
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
    entry_name_key_to_speaker_ids: dict[str, list[Optional[int]]],
) -> Optional[LeaveEntrySpeakerLink]:
    if parliament_number is not None:
        canonical_name = lookups.direct.get(
            (period_normalize(strip_title(normalize_name(name))), parliament_number)
        )
        if canonical_name is not None:
            return LeaveEntrySpeakerLink(
                name_parliament_number_to_speaker_id[
                    (canonical_name, parliament_number)
                ],
                LeaveSpeakerLinkSource.ROSTER_NAME,
            )
    speaker_ids = entry_name_key_to_speaker_ids.get(get_leave_name_key(name), [])
    if len(speaker_ids) != 1:
        return None
    if speaker_ids[0] is None:
        return None
    return LeaveEntrySpeakerLink(
        speaker_ids[0], LeaveSpeakerLinkSource.SITTING_ATTENDANCE_ENTRY
    )
