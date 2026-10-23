from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Optional, Union

from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from crud.report import CRUDReport
from database.init import engine
from database.report import Report
from logs import logger
from schemas.sample_sets import SampleSets
from services.report import build_report
from services.speech import get_speeches, get_start_of_speech_line

_SAMPLE_FILE_PATH = Path("sample.json")
_SEPARATOR_WIDTH = 90
_SNIPPET_LENGTH = 500
_SNIPPET_LINES_SHOWN = 15
_PERCENT = 100


@dataclass
class _SanityStats:
    total: int = 0
    no_hansard_website_response: int = 0
    no_content: int = 0
    no_markdown: int = 0
    no_start_line: int = 0
    no_speeches: int = 0
    invalid_speeches: int = 0
    title_mismatch: int = 0
    subtitle_mismatch: int = 0
    passed: int = 0


@dataclass(frozen=True)
class _MissingHansardWebsiteResponse:
    report_id: str
    report_type: str


@dataclass(frozen=True)
class _FailedReport:
    report_id: str
    report_type: str
    checks: list[str]
    title_stored: str
    title_regenerated: str
    subtitle_stored: Optional[str]
    subtitle_regenerated: Optional[str]
    markdown_snippet: str


def _get_start_line(report: Report) -> Optional[int]:
    if not report.markdown_content:
        return None
    return get_start_of_speech_line(
        report.markdown_content,
        report.title,
        report.subtitle,
        report.original_title,
        report.report_type,
        report.report_version,
    )


class _Check(StrEnum):
    NO_MARKDOWN = "NO_MARKDOWN"
    TITLE_MISMATCH = "TITLE_MISMATCH"
    SUBTITLE_MISMATCH = "SUBTITLE_MISMATCH"
    NO_START_LINE = "NO_START_LINE"
    NO_SPEECHES = "NO_SPEECHES"
    INVALID_SPEECHES = "INVALID_SPEECHES"
    OK = "OK"


def run_sanity_check() -> None:
    sample_sets = SampleSets.model_validate_json(_SAMPLE_FILE_PATH.read_text())
    report_ids = sample_sets.pilot + sample_sets.held_out + sample_sets.regression

    with Session(engine) as session:
        stored_reports = CRUDReport(session).get_by_ids(report_ids)
        report_id_strings = {stored_report.report_id for stored_report in stored_reports}

        hansard_website_responses = CRUDHansardWebsiteResponse(session).get_by_report_ids(report_id_strings)
    report_id_to_hansard_website_response = {hansard_website_response.report_id: hansard_website_response for hansard_website_response in hansard_website_responses}

    logger.info(f"Sample Report IDs:       {len(report_ids)}")
    logger.info(f"Stored Reports found:    {len(stored_reports)}")
    logger.info(f"Matching HWRs found:     {len(hansard_website_responses)}")
    logger.info("")

    issues: list[Union[_MissingHansardWebsiteResponse, _FailedReport]] = []
    stats = _SanityStats()

    logger.info(f"{'report_id':<14} {'type':<22} {'md':>2} {'sl':>2} {'sp':>4} {'v':>2}  checks")
    logger.info("-" * _SEPARATOR_WIDTH)

    for stored_report in sorted(stored_reports, key=lambda stored_report: stored_report.report_type):
        hansard_website_response = report_id_to_hansard_website_response.get(stored_report.report_id)
        stats.total += 1

        if hansard_website_response is None:
            stats.no_hansard_website_response += 1
            issues.append(_MissingHansardWebsiteResponse(stored_report.report_id, stored_report.report_type))
            logger.info(f"{stored_report.report_id:<14} {stored_report.report_type:<22} {'?':>2} {'?':>2} {'?':>4} {'?':>2}  NO HansardWebsiteResponse found")
            continue

        if hansard_website_response.content is None:
            stats.no_content += 1
            logger.info(f"{stored_report.report_id:<14} {stored_report.report_type:<22} {'-':>2} {'-':>2} {'-':>4} {'-':>2}  no content (expected for some types)")
            continue

        regenerated_report = build_report(hansard_website_response)

        checks = []

        if regenerated_report.markdown_content is None:
            stats.no_markdown += 1
            checks.append(_Check.NO_MARKDOWN.value)
        markdown_flag = "Y" if regenerated_report.markdown_content else "N"

        if regenerated_report.title != stored_report.title:
            stats.title_mismatch += 1
            checks.append(f"{_Check.TITLE_MISMATCH}(stored={stored_report.title!r} regen={regenerated_report.title!r})")

        if regenerated_report.subtitle != stored_report.subtitle:
            stats.subtitle_mismatch += 1
            checks.append(f"{_Check.SUBTITLE_MISMATCH}(stored={stored_report.subtitle!r} regen={regenerated_report.subtitle!r})")

        start_line = _get_start_line(regenerated_report)
        if start_line is None and regenerated_report.markdown_content:
            stats.no_start_line += 1
            checks.append(_Check.NO_START_LINE.value)

        speeches = (
            []
            if start_line is None
            else get_speeches(
                regenerated_report.markdown_content, start_line, regenerated_report.report_type, regenerated_report.report_version
            )
        )
        if start_line is not None and len(speeches) == 0:
            stats.no_speeches += 1
            checks.append(_Check.NO_SPEECHES.value)
        invalid = [speech for speech in speeches if not speech.speaker or not speech.transcript.strip()]
        if invalid:
            stats.invalid_speeches += 1
            checks.append(f"{_Check.INVALID_SPEECHES}({len(invalid)})")

        is_failed = bool(checks)
        speech_count = "-" if start_line is None else str(len(speeches))
        valid_flag = "-" if start_line is None else ("N" if is_failed else "Y")

        if not is_failed:
            stats.passed += 1
            checks.append(_Check.OK.value)

        start_line_flag = "Y" if start_line is not None else "N"
        checks_text = "  ".join(checks)
        logger.info(f"{stored_report.report_id:<14} {stored_report.report_type:<22} {markdown_flag:>2} {start_line_flag:>2} {speech_count:>4} {valid_flag:>2}  {checks_text}")

        if is_failed:
            issues.append(_FailedReport(
                stored_report.report_id,
                stored_report.report_type,
                checks,
                stored_report.title,
                regenerated_report.title,
                stored_report.subtitle,
                regenerated_report.subtitle,
                (regenerated_report.markdown_content or "")[:_SNIPPET_LENGTH],
            ))

    logger.info("")
    logger.info("=" * _SEPARATOR_WIDTH)
    logger.info(f"Total records:         {stats.total}")
    logger.info(f"No matching HWR:       {stats.no_hansard_website_response}")
    logger.info(f"No content:            {stats.no_content}")
    logger.info(f"No markdown generated: {stats.no_markdown}")
    logger.info(f"No start line:         {stats.no_start_line}")
    logger.info(f"No speeches:           {stats.no_speeches}")
    logger.info(f"Invalid speeches:      {stats.invalid_speeches}")
    logger.info(f"Title mismatches:      {stats.title_mismatch}")
    logger.info(f"Subtitle mismatches:   {stats.subtitle_mismatch}")
    logger.info(f"PASS:                  {stats.passed}")
    logger.info("")

    content_records = stats.total - stats.no_hansard_website_response - stats.no_content
    if content_records > 0:
        pass_rate = stats.passed / content_records * _PERCENT
        logger.info(f"Pass rate (content records): {stats.passed}/{content_records} = {pass_rate:.1f}%")

    if issues:
        logger.info("")
        logger.info("=== ISSUE DETAILS ===")
        for issue in issues:
            if isinstance(issue, _MissingHansardWebsiteResponse):
                logger.info(f"\n  [NO HWR]  report_id={issue.report_id} type={issue.report_type}")
                continue
            logger.info(f"\n  report_id={issue.report_id}  type={issue.report_type}")
            logger.info(f"  checks: {issue.checks}")
            if _Check.TITLE_MISMATCH in str(issue.checks):
                logger.info(f"  title stored: {issue.title_stored!r}")
                logger.info(f"  title regen:  {issue.title_regenerated!r}")
            if _Check.SUBTITLE_MISMATCH in str(issue.checks):
                logger.info(f"  subtitle stored: {issue.subtitle_stored!r}")
                logger.info(f"  subtitle regen:  {issue.subtitle_regenerated!r}")
            if _Check.NO_START_LINE in str(issue.checks) or _Check.NO_SPEECHES in str(issue.checks):
                logger.info("  markdown snippet:")
                for line in issue.markdown_snippet.splitlines()[:_SNIPPET_LINES_SHOWN]:
                    logger.info(f"    {line}")


if __name__ == "__main__":
    run_sanity_check()
