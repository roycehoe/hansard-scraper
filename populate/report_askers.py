from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from typing import Sequence, Union

from sqlmodel import Session

from crud.report import CRUDReport, ReportAskerReportRow
from crud.report_asker import CRUDReportAsker, ReportAskerRow
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechAskerRow
from database.report_asker import ReportAsker
from enums import ReportAskerSource, ReportType
from exceptions import HansardWriteCheckError
from logs import logger
from services.attendance import build_speaker_lookups
from services.attribution import get_group
from services.report_asker import build_report_askers, get_asker_candidates
from services.speaker_link import resolve_speech_speaker_id
from utils.asker_candidate import AskerCandidate
from utils.speaker_resolution import SpeakerLookups

REPORT_ASKER_REPORT_TYPES = (
    ReportType.ORAL_ANSWER,
    ReportType.WRITTEN_ANSWER,
    ReportType.WRITTEN_ANSWER_NOT_AVAILABLE,
)
_REPORT_BATCH = 200


@dataclass
class ReportAskerCounts:
    reports: int = 0
    reports_with_resolved_asker: int = 0
    source_to_row_count: Counter[ReportAskerSource] = field(default_factory=Counter)
    rows_without_speaker_id: int = 0
    rows_with_reader: int = 0
    stood_rows_with_reader: int = 0
    stood_rows_without_reader: int = 0


@dataclass(frozen=True)
class ReportAskerPlan:
    report_ids: list[int] = field(default_factory=list)
    report_askers: list[ReportAsker] = field(default_factory=list)
    group_to_counts: defaultdict[str, ReportAskerCounts] = field(
        default_factory=lambda: defaultdict(ReportAskerCounts)
    )


def _resolve_candidate(
    asker_candidate: AskerCandidate,
    report_row: ReportAskerReportRow,
    lookups: SpeakerLookups,
    name_parliament_number_to_speaker_id: dict[tuple[str, int], int],
) -> AskerCandidate:
    if (
        asker_candidate.source != ReportAskerSource.STOOD_IN_NAME_LINE
        and asker_candidate.source != ReportAskerSource.NAME_IN_TEXT
    ):
        return asker_candidate
    return replace(
        asker_candidate,
        speaker_id=resolve_speech_speaker_id(
            asker_candidate.printed_name,
            report_row.parliament_number,
            report_row.sitting_date,
            lookups,
            name_parliament_number_to_speaker_id,
        ),
    )


def _add_report(
    counts: ReportAskerCounts,
    report_askers: Sequence[Union[ReportAsker, ReportAskerRow]],
) -> None:
    counts.reports += 1
    counts.reports_with_resolved_asker += any(
        report_asker.speaker_id is not None for report_asker in report_askers
    )
    for report_asker in report_askers:
        counts.source_to_row_count[report_asker.source] += 1
        counts.rows_without_speaker_id += report_asker.speaker_id is None
        counts.rows_with_reader += report_asker.reader_printed_name is not None
        if report_asker.source != ReportAskerSource.STOOD_IN_NAME_LINE:
            continue
        if report_asker.reader_printed_name is None:
            counts.stood_rows_without_reader += 1
            continue
        counts.stood_rows_with_reader += 1


def get_report_asker_plan(session: Session, report_ids: list[int]) -> ReportAskerPlan:
    speakers = CRUDSpeaker(session).get_all()
    name_parliament_number_to_speaker_id = {
        (speaker.name, speaker.parliament_number): speaker.id
        for speaker in speakers
        if speaker.id is not None
    }
    lookups = build_speaker_lookups(speakers)
    plan = ReportAskerPlan()
    sorted_report_ids = sorted(report_ids)
    for start in range(0, len(sorted_report_ids), _REPORT_BATCH):
        report_rows = CRUDReport(session).get_asker_report_rows_by_ids_and_report_types(
            sorted_report_ids[start : start + _REPORT_BATCH],
            REPORT_ASKER_REPORT_TYPES,
        )
        report_id_to_speech_asker_rows: defaultdict[int, list[SpeechAskerRow]] = (
            defaultdict(list)
        )
        for speech_asker_row in CRUDSpeech(session).get_asker_rows_by_report_ids(
            [report_row.id for report_row in report_rows]
        ):
            report_id_to_speech_asker_rows[speech_asker_row.report_id].append(
                speech_asker_row
            )
        for report_row in report_rows:
            report_askers = build_report_askers(
                report_row.id,
                [
                    _resolve_candidate(
                        asker_candidate,
                        report_row,
                        lookups,
                        name_parliament_number_to_speaker_id,
                    )
                    for asker_candidate in get_asker_candidates(
                        report_id_to_speech_asker_rows[report_row.id],
                        report_row.title,
                    )
                ],
            )
            _add_report(
                plan.group_to_counts[get_group(report_row.parliament_number)],
                report_askers,
            )
            plan.report_ids.append(report_row.id)
            plan.report_askers.extend(report_askers)
    return plan


def _get_stored_counts(
    session: Session, report_ids: list[int]
) -> defaultdict[str, ReportAskerCounts]:
    group_to_counts: defaultdict[str, ReportAskerCounts] = defaultdict(
        ReportAskerCounts
    )
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch_report_ids = report_ids[start : start + _REPORT_BATCH]
        report_id_to_report_asker_rows: defaultdict[int, list[ReportAskerRow]] = (
            defaultdict(list)
        )
        for report_asker_row in CRUDReportAsker(session).get_rows_by_report_ids(
            batch_report_ids
        ):
            report_id_to_report_asker_rows[report_asker_row.report_id].append(
                report_asker_row
            )
        for report_row in CRUDReport(
            session
        ).get_asker_report_rows_by_ids_and_report_types(
            batch_report_ids, REPORT_ASKER_REPORT_TYPES
        ):
            _add_report(
                group_to_counts[get_group(report_row.parliament_number)],
                report_id_to_report_asker_rows[report_row.id],
            )
    return group_to_counts


def _validate_can_commit_report_askers(session: Session, plan: ReportAskerPlan) -> None:
    stored_group_to_counts = _get_stored_counts(session, plan.report_ids)
    for group, counts in plan.group_to_counts.items():
        stored_counts = stored_group_to_counts[group]
        if stored_counts.source_to_row_count != counts.source_to_row_count:
            raise HansardWriteCheckError(
                f"{group}: stored report askers by source {dict(stored_counts.source_to_row_count)}, the plan has {dict(counts.source_to_row_count)}"
            )
        if (
            stored_counts.reports_with_resolved_asker
            != counts.reports_with_resolved_asker
        ):
            raise HansardWriteCheckError(
                f"{group}: {stored_counts.reports_with_resolved_asker} reports hold a resolved asker, the plan has {counts.reports_with_resolved_asker}"
            )
        if stored_counts.rows_without_speaker_id != counts.rows_without_speaker_id:
            raise HansardWriteCheckError(
                f"{group}: {stored_counts.rows_without_speaker_id} report askers hold no speaker_id, the plan has {counts.rows_without_speaker_id}"
            )
        if stored_counts.rows_with_reader != counts.rows_with_reader:
            raise HansardWriteCheckError(
                f"{group}: {stored_counts.rows_with_reader} report askers hold a reader, the plan has {counts.rows_with_reader}"
            )


def _insert_report_askers(session: Session, plan: ReportAskerPlan) -> None:
    CRUDReportAsker(session).add_many(plan.report_askers)
    _validate_can_commit_report_askers(session, plan)


def write_report_asker_plan(session: Session, plan: ReportAskerPlan) -> None:
    for start in range(0, len(plan.report_ids), _REPORT_BATCH):
        batch_report_ids = plan.report_ids[start : start + _REPORT_BATCH]
        stored_count = len(
            CRUDReportAsker(session).get_rows_by_report_ids(batch_report_ids)
        )
        deleted_count = CRUDReportAsker(session).delete_by_report_ids(batch_report_ids)
        if deleted_count != stored_count:
            raise HansardWriteCheckError(
                f"Deleted {deleted_count} report askers, read {stored_count}"
            )
    _insert_report_askers(session, plan)


# NOTE: inserts only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_report_askers(session: Session, report_ids: list[int]) -> None:
    plan = get_report_asker_plan(session, report_ids)
    _insert_report_askers(session, plan)
    logger.info(
        f"Report askers: added {len(plan.report_askers)} rows for {len(plan.report_ids)} reports"
    )
