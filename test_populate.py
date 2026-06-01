import csv
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

import database.handsard_sitting_date_response  # noqa: F401
import database.handsard_website_response  # noqa: F401
import database.parsing_statistics  # noqa: F401
import database.report  # noqa: F401
import database.sitting  # noqa: F401
import database.sitting_a2b  # noqa: F401
import database.sitting_annexure  # noqa: F401
import database.sitting_attendance  # noqa: F401
import database.sitting_ptba  # noqa: F401
import database.sitting_section  # noqa: F401
import database.sitting_vernacular  # noqa: F401
import database.speech  # noqa: F401
from crud.handsard_sitting_date_response import CRUDHandsardSittingDateResponse
from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from crud.parsing_statistics import CRUDParsingStatistics
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from crud.sitting_a2b import CRUDSittingA2b
from crud.sitting_annexure import CRUDSittingAnnexure
from crud.sitting_attendance import CRUDSittingAttendance
from crud.sitting_ptba import CRUDSittingPtba
from crud.sitting_section import CRUDSittingSection
from crud.sitting_vernacular import CRUDSittingVernacular
from crud.speech import CRUDSpeech
from database.parsing_statistics import ParsingStatistics
from database.speech import Speech
from exceptions import HansardGatewayError
from gateway.handsard_report import get_handsard_report_response
from gateway.handsard_search import get_handsard_search_results
from logs import logger
from schemas.handsard_search_result import HandsardSearchResult
from services.handsard_sitting_date_response import (
    build_new_handsard_sitting_date_response,
    build_old_handsard_sitting_date_response,
)
from services.handsard_website import build_handsard_website_response
from services.report import build_report
from services.sitting import build_sitting
from services.speech import get_speeches, get_start_of_speech_line
from settings import settings

LOCAL_DATABASE_URL = "postgresql://user:password@localhost:5432/postgres"
SAMPLE_SIZE = 30

engine = create_engine(url=LOCAL_DATABASE_URL)


def create_tables():
    SQLModel.metadata.create_all(engine)


def populate_handsard_responses(session: Session):
    raw = get_handsard_search_results(0, 19) + get_handsard_search_results(20, 39)
    results = [HandsardSearchResult(**r) for r in raw[:SAMPLE_SIZE]]
    crud = CRUDHandsardWebsiteResponse(session)
    for i, result in enumerate(results, start=1):
        logger.info(f"{i}/{len(results)}")
        crud.create(build_handsard_website_response(result))


def populate_reports(session: Session):
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    crud = CRUDReport(session)
    for i, response in enumerate(responses, start=1):
        logger.info(f"{i}/{len(responses)}")
        crud.create(build_report(response))


def _get_statistics(response):
    report = build_report(response)
    has_markdown = report.markdown_content is not None
    has_start_line = False
    can_get_speeches = False
    if has_markdown:
        start_of_speech_line = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle,
            report.original_title, report.report_type,
        )
        has_start_line = start_of_speech_line is not None
        if has_start_line:
            get_speeches(report.markdown_content, start_of_speech_line, report.report_type)
            can_get_speeches = True
    return ParsingStatistics(
        **report.model_dump(),
        has_markdown=has_markdown,
        has_start_line=has_start_line,
        can_get_speeches=can_get_speeches,
    )


def populate_statistics(session: Session):
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    crud = CRUDParsingStatistics(session)
    for i, response in enumerate(responses, start=1):
        logger.info(f"{i}/{len(responses)}")
        crud.create(_get_statistics(response))


def export_statistics_csv(session: Session, path: str = "statistics.csv"):
    all_statistics = CRUDParsingStatistics(session).get_all()
    if not all_statistics:
        return
    fieldnames = list(all_statistics[0].model_dump().keys())
    with open(path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for item in all_statistics:
            writer.writerow(item.model_dump())


def populate_speeches(session: Session):
    db_reports = CRUDReport(session).get_all()
    crud = CRUDSpeech(session)
    for i, db_report in enumerate(db_reports, start=1):
        logger.info(f"{i}/{len(db_reports)}")
        if db_report.markdown_content is None:
            continue
        start_of_speech_line = get_start_of_speech_line(
            db_report.markdown_content, db_report.title, db_report.subtitle,
            db_report.original_title, db_report.report_type,
        )
        if start_of_speech_line is None:
            continue
        for ordinal, speech in enumerate(
            get_speeches(db_report.markdown_content, start_of_speech_line, db_report.report_type)
        ):
            crud.create(Speech(
                ordinal=ordinal + 1,
                speaker=speech.speaker,
                transcript=speech.transcript,
                report_id=db_report.id,
            ))


def populate_handsard_sitting_dates(session: Session):
    all_sitting_dates = CRUDHandsardWebsiteResponse(session).get_all_sitting_dates()
    existing_sitting_dates = CRUDHandsardSittingDateResponse(session).get_all_sitting_dates()
    dates_to_fetch = list(all_sitting_dates - existing_sitting_dates)

    sitting_crud = CRUDHandsardSittingDateResponse(session)
    attendance_crud = CRUDSittingAttendance(session)
    ptba_crud = CRUDSittingPtba(session)
    section_crud = CRUDSittingSection(session)
    annexure_crud = CRUDSittingAnnexure(session)
    vernacular_crud = CRUDSittingVernacular(session)
    a2b_crud = CRUDSittingA2b(session)

    for i, sitting_date in enumerate(dates_to_fetch, start=1):
        logger.info(f"{i}/{len(dates_to_fetch)}: {sitting_date}")
        try:
            result = get_handsard_report_response(sitting_date)
        except HansardGatewayError as e:
            logger.warning(f"Skipping {sitting_date}: {e}")
            continue

        if datetime.strptime(sitting_date, "%d-%m-%Y") >= settings.sitting_date_format_change:
            data = build_new_handsard_sitting_date_response(result, sitting_date)
        else:
            data = build_old_handsard_sitting_date_response(result, sitting_date)
        sitting_crud.create(data.response)
        sitting_id = data.response.id

        for record in data.attendance:
            record.sitting_id = sitting_id
            attendance_crud.create(record)
        for record in data.ptba:
            record.sitting_id = sitting_id
            ptba_crud.create(record)
        for record in data.sections:
            record.sitting_id = sitting_id
            section_crud.create(record)
        for record in data.annexures:
            record.sitting_id = sitting_id
            annexure_crud.create(record)
        for record in data.vernaculars:
            record.sitting_id = sitting_id
            vernacular_crud.create(record)
        for record in data.a2b:
            record.sitting_id = sitting_id
            a2b_crud.create(record)


def populate_sittings(session: Session):
    sitting_dates = list(CRUDHandsardWebsiteResponse(session).get_all_sitting_dates())
    crud = CRUDSitting(session)
    for i, sitting_date in enumerate(sitting_dates, start=1):
        logger.info(f"{i}/{len(sitting_dates)}: {sitting_date}")
        try:
            result = get_handsard_report_response(sitting_date)
        except HansardGatewayError as e:
            logger.warning(f"Skipping {sitting_date}: {e}")
            continue
        if datetime.strptime(sitting_date, "%d-%m-%Y") >= settings.sitting_date_format_change:
            data = build_new_handsard_sitting_date_response(result, sitting_date)
        else:
            data = build_old_handsard_sitting_date_response(result, sitting_date)
        crud.create(build_sitting(data.response))


if __name__ == "__main__":
    create_tables()
    with Session(engine) as session:
        populate_handsard_responses(session)
        populate_reports(session)
        populate_statistics(session)
        export_statistics_csv(session)
        populate_speeches(session)
        populate_handsard_sitting_dates(session)
        populate_sittings(session)
