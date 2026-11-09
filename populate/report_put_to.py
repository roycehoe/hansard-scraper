from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session

from crud.report import CRUDReport
from crud.report_put_to import CRUDReportPutTo
from crud.speech import CRUDSpeech, SpeechAskerRow
from database.report_put_to import ReportPutTo
from enums import ReportPutToSource, ReportType
from exceptions import HansardWriteCheckError
from logs import logger
from services.report_asker import get_question_row_ordinals
from services.report_put_to import get_put_to_phrases
from utils.sitting_dates import get_decade

REPORT_PUT_TO_REPORT_TYPES = (
    ReportType.ORAL_ANSWER,
    ReportType.WRITTEN_ANSWER,
    ReportType.WRITTEN_ANSWER_NOT_AVAILABLE,
)
_REPORT_BATCH = 200


@dataclass(frozen=True)
class ReportPutToPlan:
    sprs_report_ids: list[str]
    sprs_report_id_to_sitting_date: dict[str, datetime]
    report_put_tos: list[ReportPutTo]
    decade_to_row_count: Counter[int]
    source_to_row_count: Counter[ReportPutToSource]
    reports_without_phrase: int


def get_report_put_to_plan(session: Session, report_ids: list[int]) -> ReportPutToPlan:
    sprs_report_ids: list[str] = []
    sprs_report_id_to_sitting_date: dict[str, datetime] = {}
    report_put_tos: list[ReportPutTo] = []
    decade_to_row_count: Counter[int] = Counter()
    source_to_row_count: Counter[ReportPutToSource] = Counter()
    reports_without_phrase = 0
    sorted_report_ids = sorted(report_ids)
    for start in range(0, len(sorted_report_ids), _REPORT_BATCH):
        report_rows = CRUDReport(
            session
        ).get_put_to_report_rows_by_ids_and_report_types(
            sorted_report_ids[start : start + _REPORT_BATCH],
            REPORT_PUT_TO_REPORT_TYPES,
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
            speech_asker_rows = report_id_to_speech_asker_rows[report_row.id]
            put_to_phrases = get_put_to_phrases(
                speech_asker_rows, get_question_row_ordinals(speech_asker_rows)
            )
            if not put_to_phrases:
                reports_without_phrase += 1
            decade = get_decade(report_row.sitting_date)
            for ordinal, put_to_phrase in enumerate(put_to_phrases, start=1):
                report_put_tos.append(
                    ReportPutTo(
                        ordinal=ordinal,
                        office_printed=put_to_phrase.office_printed,
                        printed_text=put_to_phrase.printed_text,
                        source=put_to_phrase.source,
                        first_ordinal=put_to_phrase.first_ordinal,
                        sprs_report_id=report_row.report_id,
                    )
                )
                decade_to_row_count[decade] += 1
                source_to_row_count[put_to_phrase.source] += 1
            sprs_report_ids.append(report_row.report_id)
            sprs_report_id_to_sitting_date[report_row.report_id] = (
                report_row.sitting_date
            )
    return ReportPutToPlan(
        sprs_report_ids,
        sprs_report_id_to_sitting_date,
        report_put_tos,
        decade_to_row_count,
        source_to_row_count,
        reports_without_phrase,
    )


def _validate_can_commit_report_put_to(session: Session, plan: ReportPutToPlan) -> None:
    stored_decade_to_row_count: Counter[int] = Counter()
    stored_source_to_row_count: Counter[ReportPutToSource] = Counter()
    for start in range(0, len(plan.sprs_report_ids), _REPORT_BATCH):
        for report_put_to_row in CRUDReportPutTo(session).get_rows_by_sprs_report_ids(
            plan.sprs_report_ids[start : start + _REPORT_BATCH]
        ):
            stored_decade_to_row_count[
                get_decade(
                    plan.sprs_report_id_to_sitting_date[
                        report_put_to_row.sprs_report_id
                    ]
                )
            ] += 1
            stored_source_to_row_count[report_put_to_row.source] += 1
    if stored_decade_to_row_count != plan.decade_to_row_count:
        raise HansardWriteCheckError(
            f"Stored report put-tos by decade {dict(stored_decade_to_row_count)}, the plan has {dict(plan.decade_to_row_count)}"
        )
    if stored_source_to_row_count != plan.source_to_row_count:
        raise HansardWriteCheckError(
            f"Stored report put-tos by source {dict(stored_source_to_row_count)}, the plan has {dict(plan.source_to_row_count)}"
        )


def _insert_report_put_to(session: Session, plan: ReportPutToPlan) -> None:
    for start in range(0, len(plan.report_put_tos), _REPORT_BATCH):
        CRUDReportPutTo(session).add_many(
            plan.report_put_tos[start : start + _REPORT_BATCH]
        )
    _validate_can_commit_report_put_to(session, plan)


def write_report_put_to_plan(session: Session, plan: ReportPutToPlan) -> None:
    for start in range(0, len(plan.sprs_report_ids), _REPORT_BATCH):
        batch_sprs_report_ids = plan.sprs_report_ids[start : start + _REPORT_BATCH]
        stored_report_put_to_count = len(
            CRUDReportPutTo(session).get_rows_by_sprs_report_ids(batch_sprs_report_ids)
        )
        deleted_report_put_to_count = CRUDReportPutTo(
            session
        ).delete_by_sprs_report_ids(batch_sprs_report_ids)
        if deleted_report_put_to_count != stored_report_put_to_count:
            raise HansardWriteCheckError(
                f"Deleted {deleted_report_put_to_count} report put-tos, read {stored_report_put_to_count}"
            )
    _insert_report_put_to(session, plan)


# NOTE: inserts only, because the refresh role has no DELETE grant and Postgres checks it per statement
def populate_report_put_to(session: Session, report_ids: list[int]) -> None:
    plan = get_report_put_to_plan(session, report_ids)
    _insert_report_put_to(session, plan)
    logger.info(
        f"Report put-tos: added {len(plan.report_put_tos)} rows for {len(plan.sprs_report_ids)} reports"
    )
