from collections import Counter
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session

from crud.attendance_office import CRUDAttendanceOffice
from crud.ministry import CRUDMinistry
from crud.ministry_see_also import CRUDMinistrySeeAlso
from crud.office_title_ministry import CRUDOfficeTitleMinistry
from crud.report import CRUDReport
from crud.report_participant import CRUDReportParticipant
from crud.report_put_to import CRUDReportPutTo
from database.ministry import Ministry
from database.ministry_see_also import MinistrySeeAlso
from database.office_title_ministry import OfficeTitleMinistry
from enums import OfficeTitleMinistrySource, ReportType
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.ministry_list import MinistrySeeAlsoEntry
from services.office_title_ministry import get_office_title_placement
from utils.data_files import (
    get_ministry_names,
    get_ministry_see_also,
    get_office_title_ministries,
)

REPORT_OFFICE_TITLE_REPORT_TYPES = (
    ReportType.ORAL_ANSWER,
    ReportType.WRITTEN_ANSWER,
    ReportType.WRITTEN_ANSWER_NOT_AVAILABLE,
)


@dataclass(frozen=True)
class PlacedOfficeTitle:
    office_printed: str
    ordinal: int
    ministry_name: str
    source: OfficeTitleMinistrySource


@dataclass(frozen=True)
class MinistryPlan:
    ministry_names: list[str]
    placed_office_titles: list[PlacedOfficeTitle]
    role_only_titles: list[str]
    unplaced_titles: list[str]
    ministry_see_also_entries: list[MinistrySeeAlsoEntry]


def _get_ministry_names_longest_first(ministry_names: list[str]) -> list[str]:
    return sorted(ministry_names, key=len, reverse=True)


def _get_title_to_ministry_names() -> dict[str, list[str]]:
    return {
        office_title_ministry_entry.office_printed: office_title_ministry_entry.ministry_names
        for office_title_ministry_entry in get_office_title_ministries()
    }


def _get_placed_office_titles(
    office_printed: str,
    ministry_names_longest_first: list[str],
    title_to_ministry_names: dict[str, list[str]],
) -> Optional[list[PlacedOfficeTitle]]:
    placements = get_office_title_placement(
        office_printed, ministry_names_longest_first, title_to_ministry_names
    )
    if placements is None:
        return None
    return [
        PlacedOfficeTitle(
            office_printed, ordinal, placement.ministry_name, placement.source
        )
        for ordinal, placement in enumerate(placements, 1)
    ]


def get_ministry_plan(session: Session) -> MinistryPlan:
    ministry_names = get_ministry_names()
    ministry_names_longest_first = _get_ministry_names_longest_first(ministry_names)
    title_to_ministry_names = _get_title_to_ministry_names()
    office_printed_values = sorted(
        set(CRUDAttendanceOffice(session).get_distinct_office_printed())
        | set(CRUDReportPutTo(session).get_distinct_office_printed())
        | set(CRUDReportParticipant(session).get_distinct_office_printed())
    )
    placed_office_titles: list[PlacedOfficeTitle] = []
    role_only_titles: list[str] = []
    unplaced_titles: list[str] = []
    for office_printed in office_printed_values:
        title_placed_office_titles = _get_placed_office_titles(
            office_printed, ministry_names_longest_first, title_to_ministry_names
        )
        if title_placed_office_titles is None:
            unplaced_titles.append(office_printed)
            continue
        if not title_placed_office_titles:
            role_only_titles.append(office_printed)
            continue
        placed_office_titles.extend(title_placed_office_titles)
    return MinistryPlan(
        ministry_names,
        placed_office_titles,
        role_only_titles,
        unplaced_titles,
        get_ministry_see_also(),
    )


def _validate_can_commit_ministries(session: Session, plan: MinistryPlan) -> None:
    ministries = CRUDMinistry(session).get_all()
    if sorted(ministry.name for ministry in ministries) != sorted(plan.ministry_names):
        raise HansardWriteCheckError(
            f"Stored ministry names {sorted(ministry.name for ministry in ministries)}, the file has {sorted(plan.ministry_names)}"
        )
    ministry_id_to_name = {ministry.id: ministry.name for ministry in ministries}
    stored_placements = Counter(
        (
            office_title_ministry_row.office_printed,
            ministry_id_to_name[office_title_ministry_row.ministry_id],
            office_title_ministry_row.source,
        )
        for office_title_ministry_row in CRUDOfficeTitleMinistry(session).get_rows()
    )
    planned_placements = Counter(
        (
            placed_office_title.office_printed,
            placed_office_title.ministry_name,
            placed_office_title.source,
        )
        for placed_office_title in plan.placed_office_titles
    )
    if stored_placements != planned_placements:
        raise HansardWriteCheckError(
            f"Stored office title placements differ from the plan: {sum((stored_placements - planned_placements).values())} stored rows not in the plan, {sum((planned_placements - stored_placements).values())} planned rows not stored"
        )


def _get_ministry_id(ministry_name_to_id: dict[str, int], ministry_name: str) -> int:
    try:
        return ministry_name_to_id[ministry_name]
    except KeyError as error:
        raise HansardWriteCheckError(
            f"Ministry {ministry_name!r} is not in the ministry table"
        ) from error


def write_ministry_plan(session: Session, plan: MinistryPlan) -> None:
    stored_office_title_ministry_count = len(
        CRUDOfficeTitleMinistry(session).get_rows()
    )
    deleted_office_title_ministry_count = CRUDOfficeTitleMinistry(session).delete_all()
    if deleted_office_title_ministry_count != stored_office_title_ministry_count:
        raise HansardWriteCheckError(
            f"Deleted {deleted_office_title_ministry_count} office title ministries, read {stored_office_title_ministry_count}"
        )
    stored_ministry_see_also_count = len(CRUDMinistrySeeAlso(session).get_all())
    deleted_ministry_see_also_count = CRUDMinistrySeeAlso(session).delete_all()
    if deleted_ministry_see_also_count != stored_ministry_see_also_count:
        raise HansardWriteCheckError(
            f"Deleted {deleted_ministry_see_also_count} ministry see-alsos, read {stored_ministry_see_also_count}"
        )

    stored_ministries = CRUDMinistry(session).get_all()
    stored_ministry_names = {ministry.name for ministry in stored_ministries}
    removed_ministry_ids = [
        ministry.id
        for ministry in stored_ministries
        if ministry.id is not None and ministry.name not in plan.ministry_names
    ]
    stored_removed_ministry_count = len(removed_ministry_ids)
    deleted_ministry_count = CRUDMinistry(session).delete_by_ids(removed_ministry_ids)
    if deleted_ministry_count != stored_removed_ministry_count:
        raise HansardWriteCheckError(
            f"Deleted {deleted_ministry_count} ministries, read {stored_removed_ministry_count}"
        )
    CRUDMinistry(session).add_many(
        [
            Ministry(name=ministry_name)
            for ministry_name in dict.fromkeys(plan.ministry_names)
            if ministry_name not in stored_ministry_names
        ]
    )

    ministry_name_to_id = {
        ministry.name: ministry.id
        for ministry in CRUDMinistry(session).get_all()
        if ministry.id is not None
    }
    CRUDOfficeTitleMinistry(session).add_many(
        [
            OfficeTitleMinistry(
                office_printed=placed_office_title.office_printed,
                ordinal=placed_office_title.ordinal,
                source=placed_office_title.source,
                ministry_id=_get_ministry_id(
                    ministry_name_to_id, placed_office_title.ministry_name
                ),
            )
            for placed_office_title in plan.placed_office_titles
        ]
    )
    CRUDMinistrySeeAlso(session).add_many(
        [
            MinistrySeeAlso(
                note=ministry_see_also_entry.note,
                source_url=ministry_see_also_entry.source_url,
                ministry_id=_get_ministry_id(
                    ministry_name_to_id, ministry_see_also_entry.ministry_name
                ),
                see_also_ministry_id=_get_ministry_id(
                    ministry_name_to_id, ministry_see_also_entry.see_also_ministry_name
                ),
            )
            for ministry_see_also_entry in plan.ministry_see_also_entries
        ]
    )
    _validate_can_commit_ministries(session, plan)


# NOTE: inserts only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_office_title_ministries(
    session: Session, sitting_ids: list[int], report_ids: list[int]
) -> list[str]:
    sprs_report_ids = [
        put_to_report_row.report_id
        for put_to_report_row in CRUDReport(
            session
        ).get_put_to_report_rows_by_ids_and_report_types(
            report_ids, REPORT_OFFICE_TITLE_REPORT_TYPES
        )
    ]
    window_office_printed_values = (
        set(
            CRUDAttendanceOffice(session).get_distinct_office_printed_by_sitting_ids(
                sitting_ids
            )
        )
        | set(
            CRUDReportParticipant(session).get_distinct_office_printed_by_report_ids(
                report_ids
            )
        )
        | set(
            CRUDReportPutTo(session).get_distinct_office_printed_by_sprs_report_ids(
                sprs_report_ids
            )
        )
    )
    new_office_printed_values = sorted(
        window_office_printed_values
        - set(CRUDOfficeTitleMinistry(session).get_distinct_office_printed())
    )
    ministry_names_longest_first = _get_ministry_names_longest_first(get_ministry_names())
    title_to_ministry_names = _get_title_to_ministry_names()
    ministry_name_to_id = {
        ministry.name: ministry.id
        for ministry in CRUDMinistry(session).get_all()
        if ministry.id is not None
    }
    office_title_ministries: list[OfficeTitleMinistry] = []
    unplaced_titles: list[str] = []
    for office_printed in new_office_printed_values:
        placed_office_titles = _get_placed_office_titles(
            office_printed, ministry_names_longest_first, title_to_ministry_names
        )
        if placed_office_titles is None:
            unplaced_titles.append(office_printed)
            continue
        if any(
            placed_office_title.ministry_name not in ministry_name_to_id
            for placed_office_title in placed_office_titles
        ):
            unplaced_titles.append(office_printed)
            continue
        office_title_ministries.extend(
            OfficeTitleMinistry(
                office_printed=placed_office_title.office_printed,
                ordinal=placed_office_title.ordinal,
                source=placed_office_title.source,
                ministry_id=ministry_name_to_id[placed_office_title.ministry_name],
            )
            for placed_office_title in placed_office_titles
        )
    CRUDOfficeTitleMinistry(session).add_many(office_title_ministries)
    logger.info(
        f"Office title ministries: added {len(office_title_ministries)} rows for {len(new_office_printed_values) - len(unplaced_titles)} titles, {len(unplaced_titles)} unplaced"
    )
    return unplaced_titles
