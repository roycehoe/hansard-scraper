import sys

from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from database.hansard_website_response import HansardWebsiteResponse
from database.init import engine
from database.report import Report
from enums import ReportType
from logs import logger
from services.report import build_report
from services.speech import get_start_of_speech_line

_MAX_LINES_SHOWN = 60
_MAX_FAILING_SHOWN = 3
_MAX_PASSING_SHOWN = 2
_SEPARATOR_WIDTH = 60
_DEFAULT_REPORT_TYPES = (ReportType.BILL_INTRODUCTION.value, ReportType.BUDGET.value, ReportType.PRESIDENT_ADDRESS.value, ReportType.ATBP.value)


def log_report_markdown(hansard_website_response: HansardWebsiteResponse, report: Report, max_lines: int = _MAX_LINES_SHOWN) -> None:
    start_line = get_start_of_speech_line(
        report.markdown_content, report.title, report.subtitle, report.original_title,
        hansard_website_response.report_type, hansard_website_response.report_version,
    )
    logger.info(f"  id={hansard_website_response.id} report_type={hansard_website_response.report_type!r}")
    logger.info(f"  title={report.title!r}")
    logger.info(f"  subtitle={report.subtitle!r}")
    logger.info(f"  original_title={report.original_title!r}")
    logger.info(f"  has_start_line={start_line is not None} (line {start_line})")
    logger.info(f"  markdown ({len(report.markdown_content)} chars):")
    for line_number, line in enumerate(report.markdown_content.splitlines()[:max_lines]):
        logger.info(f"    {line_number:3d}: {line}")
    logger.info("")


def log_report_type_samples(session: Session, report_type: str, max_failing: int = _MAX_FAILING_SHOWN, max_passing: int = _MAX_PASSING_SHOWN) -> None:
    hansard_website_responses = CRUDHansardWebsiteResponse(session).get_by_report_type(report_type)

    failing, passing = [], []
    for hansard_website_response in hansard_website_responses:
        report = build_report(hansard_website_response)
        if report.markdown_content is None:
            continue
        start_line = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            hansard_website_response.report_type, hansard_website_response.report_version,
        )
        if start_line is None:
            failing.append((hansard_website_response, report))
        else:
            passing.append((hansard_website_response, report))

    logger.info(f"\n{'=' * _SEPARATOR_WIDTH}")
    logger.info(f"report_type={report_type!r}: {len(failing)} failing, {len(passing)} passing (of those with markdown)")

    logger.info(f"\n--- FAILING (showing {min(max_failing, len(failing))}) ---")
    for hansard_website_response, report in failing[:max_failing]:
        log_report_markdown(hansard_website_response, report)

    logger.info(f"\n--- PASSING (showing {min(max_passing, len(passing))}) ---")
    for hansard_website_response, report in passing[:max_passing]:
        log_report_markdown(hansard_website_response, report)


def inspect_failures() -> None:
    types = sys.argv[1:] if len(sys.argv) > 1 else _DEFAULT_REPORT_TYPES
    with Session(engine) as session:
        for report_type in types:
            log_report_type_samples(session, report_type)


if __name__ == "__main__":
    inspect_failures()
