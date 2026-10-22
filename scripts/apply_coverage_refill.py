import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Optional

from sqlmodel import Session

import database.speaker  # noqa: F401 registers Speaker so the speech.speaker_id foreign key resolves
from crud.hansard_website_response import CRUDHansardWebsiteResponse
from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.init import engine
from database.report import Report
from database.speech import Speech
from exceptions import HansardWriteCheckError
from gateway.hansard_topic import get_hansard_topic_response
from logs import logger
from schemas.coverage_refill_plan import CoverageRefillPlan, FetchedHit, FetchedReport
from schemas.hansard_search_result import HansardSearchResult
from services.hansard_website import (
    build_hansard_website_response,
    get_topic_html_content,
    get_topic_id,
)
from services.report import build_report
from services.speech import build_speeches, get_speeches, get_start_of_speech_line
from settings import settings
from utils.markdown_parser import get_cleaned_report_markdown
from utils.write_target import validate_can_write


def _fetch_topic_content(report_id: str, html_file_name: Optional[str], report_version: str) -> str:
    content = get_topic_html_content(get_hansard_topic_response(get_topic_id(report_id, html_file_name, report_version)), report_version)
    if content is None:
        raise HansardWriteCheckError(f"SPRS returned no text for {report_id}")
    if content == "":
        raise HansardWriteCheckError(f"SPRS returned no text for {report_id}")
    return content


def _build_speeches(report: Report, markdown_content: str) -> list[Speech]:
    start_of_speech_line = get_start_of_speech_line(
        markdown_content,
        report.title,
        report.subtitle,
        report.original_title,
        report.report_type,
        report.report_version,
    )
    if start_of_speech_line is None:
        return []
    return build_speeches(report, get_speeches(markdown_content, start_of_speech_line, report.report_type, report.report_version))


def _validate_can_store_search_results(session: Session, search_results: list[HansardSearchResult]) -> None:
    report_ids = {search_result.report_id for search_result in search_results}
    stored_hansard_website_responses = CRUDHansardWebsiteResponse(session).get_by_report_ids(report_ids)
    if stored_hansard_website_responses:
        raise HansardWriteCheckError(f"{len(stored_hansard_website_responses)} planned hits are already stored as raw rows, first {stored_hansard_website_responses[0].report_id}")
    stored_reports = CRUDReport(session).get_by_report_ids(list(report_ids))
    if stored_reports:
        raise HansardWriteCheckError(f"{len(stored_reports)} planned hits are already stored as reports, first {stored_reports[0].report_id}")


def _get_validated_textless_reports(session: Session, report_ids: list[int]) -> list[Report]:
    reports = CRUDReport(session).get_by_ids_for_update(report_ids)
    if len(reports) != len(report_ids):
        raise HansardWriteCheckError(f"{len(reports)} of {len(report_ids)} planned reports are stored")
    stored_speech_report_ids = {speech_row.report_id for speech_row in CRUDSpeech(session).get_rows_by_report_ids(report_ids)}
    for report in reports:
        if report.content != "":
            raise HansardWriteCheckError(f"Report {report.id} already holds text")
        if report.id in stored_speech_report_ids:
            raise HansardWriteCheckError(f"Report {report.id} already has speech rows")
    return reports


def _get_plan(session: Session, search_results: list[HansardSearchResult], report_ids: list[int]) -> CoverageRefillPlan:
    _validate_can_store_search_results(session, search_results)
    fetched_hits = []
    for search_result in search_results:
        content = _fetch_topic_content(search_result.report_id, search_result.html_file_name, search_result.report_version)
        report = build_report(build_hansard_website_response(search_result, content))
        fetched_hits.append(FetchedHit(search_result=search_result, content=content, speech_count=len(_build_speeches(report, report.markdown_content))))
        logger.info(f"{len(fetched_hits)}/{len(search_results)}: {search_result.report_id}, {fetched_hits[-1].speech_count} speech rows")
    fetched_reports = []
    for report in _get_validated_textless_reports(session, report_ids):
        content = _fetch_topic_content(report.report_id, report.html_file_name, report.report_version)
        speeches = _build_speeches(report, get_cleaned_report_markdown(content, report.report_version))
        fetched_reports.append(FetchedReport(id=report.id, content=content, speech_count=len(speeches)))
        logger.info(f"Report {report.id}: {len(content)} characters, {fetched_reports[-1].speech_count} speech rows")
    return CoverageRefillPlan(fetched_hits=fetched_hits, fetched_reports=fetched_reports)


def _write_plan(plan_path: Path, plan: CoverageRefillPlan) -> None:
    plan_json = {
        "fetched_hits": [
            {"search_result": fetched_hit.search_result.model_dump(by_alias=True), "content": fetched_hit.content, "speech_count": fetched_hit.speech_count}
            for fetched_hit in plan.fetched_hits
        ],
        "fetched_reports": [
            {"id": fetched_report.id, "content": fetched_report.content, "speech_count": fetched_report.speech_count}
            for fetched_report in plan.fetched_reports
        ],
    }
    plan_path.write_text(json.dumps(plan_json, indent=1))


def _read_plan(plan_path: Path) -> CoverageRefillPlan:
    return CoverageRefillPlan.model_validate_json(plan_path.read_text())


def _validate_can_commit_speech_counts(session: Session, report_id_to_speech_count: dict[int, int]) -> None:
    speech_rows = CRUDSpeech(session).get_rows_by_report_ids(list(report_id_to_speech_count))
    stored_report_id_to_speech_count = Counter(speech_row.report_id for speech_row in speech_rows)
    for report_id, speech_count in report_id_to_speech_count.items():
        if stored_report_id_to_speech_count[report_id] != speech_count:
            raise HansardWriteCheckError(f"Report {report_id} holds {stored_report_id_to_speech_count[report_id]} speech rows, the plan has {speech_count}")


def _add_fetched_hits(session: Session, fetched_hits: list[FetchedHit]) -> dict[int, int]:
    hansard_website_responses = [build_hansard_website_response(fetched_hit.search_result, fetched_hit.content) for fetched_hit in fetched_hits]
    CRUDHansardWebsiteResponse(session).add_many(hansard_website_responses)
    reports = [build_report(hansard_website_response) for hansard_website_response in hansard_website_responses]
    CRUDReport(session).add_many(reports)
    report_id_to_speech_count = {}
    for report, fetched_hit in zip(reports, fetched_hits, strict=True):
        speeches = _build_speeches(report, report.markdown_content)
        if len(speeches) != fetched_hit.speech_count:
            raise HansardWriteCheckError(f"{report.report_id} parses to {len(speeches)} speech rows, the plan has {fetched_hit.speech_count}")
        CRUDSpeech(session).add_many(speeches)
        report_id_to_speech_count[report.id] = len(speeches)
    return report_id_to_speech_count


def _fill_fetched_reports(session: Session, fetched_reports: list[FetchedReport]) -> dict[int, int]:
    id_to_fetched_report = {fetched_report.id: fetched_report for fetched_report in fetched_reports}
    report_id_to_speech_count = {}
    for report in _get_validated_textless_reports(session, list(id_to_fetched_report)):
        fetched_report = id_to_fetched_report[report.id]
        CRUDHansardWebsiteResponse(session).set_content_by_report_id(report.report_id, fetched_report.content)
        report.content = fetched_report.content
        report.markdown_content = get_cleaned_report_markdown(fetched_report.content, report.report_version)
        CRUDReport(session).update(report)
        speeches = _build_speeches(report, report.markdown_content)
        if len(speeches) != fetched_report.speech_count:
            raise HansardWriteCheckError(f"Report {report.id} parses to {len(speeches)} speech rows, the plan has {fetched_report.speech_count}")
        CRUDSpeech(session).add_many(speeches)
        report_id_to_speech_count[report.id] = len(speeches)
    return report_id_to_speech_count


def apply_coverage_refill(plan_path: Path, hits_path: Optional[Path], report_ids: list[int], is_commit: bool) -> None:
    if not is_commit:
        search_results = [HansardSearchResult.model_validate(search_result) for search_result in json.loads(hits_path.read_text())]
        with Session(engine) as session:
            plan = _get_plan(session, search_results, report_ids)
        _write_plan(plan_path, plan)
        speech_count = sum(fetched_hit.speech_count for fetched_hit in plan.fetched_hits) + sum(fetched_report.speech_count for fetched_report in plan.fetched_reports)
        logger.info(f"Plan: {len(plan.fetched_hits)} hits to insert, {len(plan.fetched_reports)} reports to fill, {speech_count} speech rows")
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    plan = _read_plan(plan_path)
    with Session(engine) as session:
        _validate_can_store_search_results(session, [fetched_hit.search_result for fetched_hit in plan.fetched_hits])
        report_id_to_speech_count = _add_fetched_hits(session, plan.fetched_hits) | _fill_fetched_reports(session, plan.fetched_reports)
        _validate_can_commit_speech_counts(session, report_id_to_speech_count)
        session.commit()
    logger.info(
        f"Committed: {len(plan.fetched_hits)} hits inserted, {len(plan.fetched_reports)} reports filled, "
        f"{sum(report_id_to_speech_count.values())} speech rows"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Store the hits SPRS lists that the database lacks, and fill stored reports SPRS now serves text for")
    parser.add_argument("plan", type=Path, help="the plan file, holding the fetched text: written by a dry run, read by --commit")
    parser.add_argument("--hits", type=Path, help="dry run: a JSON list of the unstored search results")
    parser.add_argument("--report-id", type=int, action="append", default=[], help="dry run: a stored report with empty text to fetch again")
    parser.add_argument("--commit", action="store_true", help="check the hits are still unstored and the reports still empty, and write the plan")
    arguments = parser.parse_args()
    apply_coverage_refill(arguments.plan, arguments.hits, arguments.report_id, arguments.commit)
