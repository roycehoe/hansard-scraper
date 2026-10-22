from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from database.hansard_website_response import HansardWebsiteResponse
from database.init import engine
from database.report import Report
from logs import logger
from services.report import build_report
from services.speech import get_speeches, get_start_of_speech_line

_PERCENT = 100


@dataclass
class ReportTypeSpeechStats:
    total: int = 0
    has_markdown: int = 0
    has_start_line: int = 0
    can_get_speeches: int = 0


@dataclass(frozen=True)
class BaselineResults:
    passed: list[int] = field(default_factory=list)
    failed_start_line: list[int] = field(default_factory=list)
    failed_speeches: list[int] = field(default_factory=list)


def _get_speech_start(hansard_website_response: HansardWebsiteResponse, report: Report) -> Optional[int]:
    return (
        get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            hansard_website_response.report_type, hansard_website_response.report_version,
        )
        if report.markdown_content is not None
        else None
    )


def get_report_type_speech_stats(session: Session) -> dict[str, ReportTypeSpeechStats]:
    responses = CRUDHansardWebsiteResponse(session).get_all()
    report_type_to_counts = defaultdict(ReportTypeSpeechStats)

    for response in responses:
        report_type = response.report_type
        report_type_to_counts[report_type].total += 1
        report = build_report(response)
        start = _get_speech_start(response, report)
        if report.markdown_content is None:
            continue
        report_type_to_counts[report_type].has_markdown += 1
        if start is None:
            continue
        report_type_to_counts[report_type].has_start_line += 1
        get_speeches(report.markdown_content, start, response.report_type, response.report_version)
        report_type_to_counts[report_type].can_get_speeches += 1

    return dict(report_type_to_counts)


def run_stats_on(responses: list[HansardWebsiteResponse]) -> BaselineResults:
    baseline_results = BaselineResults()
    for response in responses:
        report = build_report(response)
        start = _get_speech_start(response, report)
        if report.markdown_content is None:
            continue
        if start is None:
            baseline_results.failed_start_line.append(response.id)
            continue
        get_speeches(report.markdown_content, start, response.report_type, response.report_version)
        baseline_results.passed.append(response.id)
    return baseline_results


def diagnose() -> None:
    with Session(engine) as session:
        logger.info("=== Setup: report_type speech stats ===")
        report_type_to_counts = get_report_type_speech_stats(session)
        no_speech_types = set()
        for report_type, speech_statistics in sorted(report_type_to_counts.items(), key=lambda entry: entry[1].has_markdown, reverse=True):
            has_markdown = speech_statistics.has_markdown
            has_start_line = speech_statistics.has_start_line
            can_get_speeches = speech_statistics.can_get_speeches
            if has_markdown > 0 and can_get_speeches == 0:
                no_speech_types.add(report_type)
                marker = " <-- ZERO SPEECHES"
            else:
                marker = ""
            logger.info(f"  {report_type:30s} total={speech_statistics.total:4d} has_md={has_markdown:4d} has_start={has_start_line:4d} speeches={can_get_speeches:4d}{marker}")

        logger.info(f"\nNo-speech report types (excluded from target): {no_speech_types}")

        logger.info("\n=== Baseline (excluding no-speech types) ===")
        all_responses = CRUDHansardWebsiteResponse(session).get_all()
        target_with_markdown = [
            response for response in all_responses
            if response.report_type not in no_speech_types and build_report(response).markdown_content is not None
        ]
        baseline = run_stats_on(target_with_markdown)
        total = len(baseline.passed) + len(baseline.failed_start_line) + len(baseline.failed_speeches)
        percentage = _PERCENT * len(baseline.passed) / total if total else 0
        logger.info(f"  Pass: {len(baseline.passed)}/{total} ({percentage:.1f}%)")
        logger.info(f"  Fail has_start_line: {len(baseline.failed_start_line)}")
        logger.info(f"  Fail can_get_speeches: {len(baseline.failed_speeches)}")


if __name__ == "__main__":
    diagnose()
