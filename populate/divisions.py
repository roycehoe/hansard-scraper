from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence, Union

from sqlmodel import Session

from crud.division import CRUDDivision
from crud.report import CRUDReport
from crud.speech import CRUDSpeech, SpeechParseRow
from database.division import Division
from enums import DivisionCountSource, DivisionListStatus
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.division_plan import DivisionPlan, PlannedDivision, PlannedUnreadRow
from services.division import get_report_divisions
from utils.division_update import DivisionUpdate

_REPORT_BATCH = 200
_YEARS_PER_DECADE = 10


@dataclass(frozen=True)
class DivisionMatch:
    division_updates: list[DivisionUpdate]
    divisions_to_add: list[Division]
    division_ids_to_delete: list[int]


@dataclass(frozen=True)
class _DivisionShape:
    report_division_number: Optional[int]
    speech_ordinal: Optional[int]
    printed_counts: str
    ayes: Optional[int]
    noes: Optional[int]
    abstentions: Optional[int]
    absent: Optional[int]
    paired: Optional[int]


def get_decade_label(sitting_date: date) -> str:
    return f"{sitting_date.year // _YEARS_PER_DECADE * _YEARS_PER_DECADE}s"


def get_decade_and_source_counts(
    divisions: Sequence[Union[Division, PlannedDivision]],
) -> Counter[tuple[str, DivisionCountSource]]:
    return Counter(
        (get_decade_label(division.sitting_date), division.count_source)
        for division in divisions
    )


def get_division_plan(session: Session, report_ids: list[int]) -> DivisionPlan:
    planned_report_ids: list[int] = []
    sprs_report_ids: list[str] = []
    planned_divisions: list[PlannedDivision] = []
    planned_unread_rows: list[PlannedUnreadRow] = []
    sorted_report_ids = sorted(report_ids)
    for start in range(0, len(sorted_report_ids), _REPORT_BATCH):
        report_rows = CRUDReport(session).get_division_report_rows_by_ids(
            sorted_report_ids[start : start + _REPORT_BATCH]
        )
        report_id_to_speech_parse_rows: defaultdict[int, list[SpeechParseRow]] = (
            defaultdict(list)
        )
        for speech_parse_row in CRUDSpeech(session).get_parse_rows_by_report_ids(
            [report_row.id for report_row in report_rows]
        ):
            report_id_to_speech_parse_rows[speech_parse_row.report_id].append(
                speech_parse_row
            )
        for report_row in report_rows:
            report_divisions = get_report_divisions(
                report_id_to_speech_parse_rows[report_row.id]
            )
            planned_report_ids.append(report_row.id)
            sprs_report_ids.append(report_row.report_id)
            planned_divisions.extend(
                PlannedDivision(
                    sprs_report_id=report_row.report_id,
                    sitting_date=report_row.sitting_date.date(),
                    parliament_number=report_row.parliament_number,
                    report_division_number=parsed_division.report_division_number,
                    speech_ordinal=parsed_division.speech_ordinal,
                    count_source=parsed_division.count_source,
                    printed_counts=parsed_division.printed_counts,
                    ayes=parsed_division.ayes,
                    noes=parsed_division.noes,
                    abstentions=parsed_division.abstentions,
                    absent=parsed_division.absent,
                    paired=parsed_division.paired,
                    list_status=DivisionListStatus.NOT_PRINTED,
                    printed_list=None,
                )
                for parsed_division in report_divisions.divisions
            )
            planned_unread_rows.extend(
                PlannedUnreadRow(
                    report_id=report_row.id,
                    sprs_report_id=report_row.report_id,
                    speech_ordinal=unread_row.speech_ordinal,
                    reason=unread_row.reason,
                    printed_text=unread_row.printed_text,
                )
                for unread_row in report_divisions.unread_rows
            )
    return DivisionPlan(
        report_ids=planned_report_ids,
        sprs_report_ids=sprs_report_ids,
        divisions=planned_divisions,
        unread_rows=planned_unread_rows,
    )


def _build_division(planned_division: PlannedDivision) -> Division:
    return Division(
        sitting_date=planned_division.sitting_date,
        parliament_number=planned_division.parliament_number,
        report_division_number=planned_division.report_division_number,
        speech_ordinal=planned_division.speech_ordinal,
        count_source=planned_division.count_source,
        printed_counts=planned_division.printed_counts,
        ayes=planned_division.ayes,
        noes=planned_division.noes,
        abstentions=planned_division.abstentions,
        absent=planned_division.absent,
        paired=planned_division.paired,
        list_status=planned_division.list_status,
        printed_list=planned_division.printed_list,
        sprs_report_id=planned_division.sprs_report_id,
    )


def _get_division_update(division_id: int, division: Division) -> DivisionUpdate:
    return DivisionUpdate(
        id=division_id,
        sitting_date=division.sitting_date,
        parliament_number=division.parliament_number,
        report_division_number=division.report_division_number,
        speech_ordinal=division.speech_ordinal,
        count_source=division.count_source,
        printed_counts=division.printed_counts,
        ayes=division.ayes,
        noes=division.noes,
        abstentions=division.abstentions,
        absent=division.absent,
        paired=division.paired,
        list_status=division.list_status,
        printed_list=division.printed_list,
    )


def get_division_match(session: Session, plan: DivisionPlan) -> DivisionMatch:
    division_id_to_stored_division: dict[int, Division] = {}
    sprs_report_id_and_printed_counts_to_stored_ids: defaultdict[
        tuple[str, str], deque[int]
    ] = defaultdict(deque)
    for stored_division in CRUDDivision(session).get_by_sprs_report_ids(
        plan.sprs_report_ids
    ):
        if stored_division.id is None or stored_division.sprs_report_id is None:
            continue
        division_id_to_stored_division[stored_division.id] = stored_division
        sprs_report_id_and_printed_counts_to_stored_ids[
            (stored_division.sprs_report_id, stored_division.printed_counts)
        ].append(stored_division.id)

    division_updates: list[DivisionUpdate] = []
    divisions_to_add: list[Division] = []
    for planned_division in plan.divisions:
        stored_ids = sprs_report_id_and_printed_counts_to_stored_ids[
            (planned_division.sprs_report_id, planned_division.printed_counts)
        ]
        division = _build_division(planned_division)
        if not stored_ids:
            divisions_to_add.append(division)
            continue
        division_id = stored_ids.popleft()
        division_update = _get_division_update(division_id, division)
        if division_update != _get_division_update(
            division_id, division_id_to_stored_division[division_id]
        ):
            division_updates.append(division_update)
    return DivisionMatch(
        division_updates,
        divisions_to_add,
        sorted(
            division_id
            for stored_ids in sprs_report_id_and_printed_counts_to_stored_ids.values()
            for division_id in stored_ids
        ),
    )


def _get_division_shape(division: Union[Division, PlannedDivision]) -> _DivisionShape:
    return _DivisionShape(
        report_division_number=division.report_division_number,
        speech_ordinal=division.speech_ordinal,
        printed_counts=division.printed_counts,
        ayes=division.ayes,
        noes=division.noes,
        abstentions=division.abstentions,
        absent=division.absent,
        paired=division.paired,
    )


def _validate_can_commit_divisions(session: Session, plan: DivisionPlan) -> None:
    stored_divisions = CRUDDivision(session).get_by_sprs_report_ids(
        plan.sprs_report_ids
    )
    stored_counts = get_decade_and_source_counts(stored_divisions)
    planned_counts = get_decade_and_source_counts(plan.divisions)
    for key in stored_counts.keys() | planned_counts.keys():
        if stored_counts[key] != planned_counts[key]:
            raise HansardWriteCheckError(
                f"{key}: {stored_counts[key]} stored divisions, the plan has {planned_counts[key]}"
            )
    sprs_report_id_to_stored_shapes: defaultdict[str, list[_DivisionShape]] = (
        defaultdict(list)
    )
    for stored_division in stored_divisions:
        if stored_division.sprs_report_id is None:
            continue
        sprs_report_id_to_stored_shapes[stored_division.sprs_report_id].append(
            _get_division_shape(stored_division)
        )
    sprs_report_id_to_planned_shapes: defaultdict[str, list[_DivisionShape]] = (
        defaultdict(list)
    )
    for planned_division in plan.divisions:
        sprs_report_id_to_planned_shapes[planned_division.sprs_report_id].append(
            _get_division_shape(planned_division)
        )
    for sprs_report_id in plan.sprs_report_ids:
        if (
            sprs_report_id_to_stored_shapes[sprs_report_id]
            != sprs_report_id_to_planned_shapes[sprs_report_id]
        ):
            raise HansardWriteCheckError(
                f"Report {sprs_report_id}: the stored divisions differ from the plan"
            )


def write_division_plan(session: Session, plan: DivisionPlan) -> None:
    match = get_division_match(session, plan)
    if match.division_ids_to_delete:
        deleted_count = CRUDDivision(session).delete_by_ids(
            match.division_ids_to_delete
        )
        if deleted_count != len(match.division_ids_to_delete):
            raise HansardWriteCheckError(
                f"Deleted {deleted_count} divisions, planned {len(match.division_ids_to_delete)}"
            )
    CRUDDivision(session).update_many(match.division_updates)
    CRUDDivision(session).add_many(match.divisions_to_add)
    _validate_can_commit_divisions(session, plan)


# NOTE: inserts only, because the refresh role has no UPDATE or DELETE grant on division
def populate_divisions(session: Session, report_ids: list[int]) -> list[int]:
    plan = get_division_plan(session, report_ids)
    CRUDDivision(session).add_many(
        [_build_division(planned_division) for planned_division in plan.divisions]
    )
    _validate_can_commit_divisions(session, plan)
    logger.info(
        f"Divisions: added {len(plan.divisions)} rows for {len(plan.report_ids)} reports"
    )
    return sorted({unread_row.report_id for unread_row in plan.unread_rows})
