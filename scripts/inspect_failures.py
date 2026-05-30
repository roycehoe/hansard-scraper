"""Manual inspection of failing documents for the refine loop."""

import sys

from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from database.init import engine
from services.report import build_report
from services.speech import get_start_of_speech_line


def show_doc(response, report, max_lines=60):
    start = get_start_of_speech_line(
        report.markdown_content, report.title, report.subtitle, report.original_title,
        response.report_type,
    )
    print(f"  id={response.id} report_type={response.report_type!r}")
    print(f"  title={report.title!r}")
    print(f"  subtitle={report.subtitle!r}")
    print(f"  original_title={report.original_title!r}")
    print(f"  has_start_line={start is not None} (line {start})")
    print(f"  markdown ({len(report.markdown_content)} chars):")
    for i, line in enumerate(report.markdown_content.splitlines()[:max_lines]):
        print(f"    {i:3d}: {line}")
    print()


def inspect_type(session: Session, report_type: str, max_failing: int = 3, max_passing: int = 2):
    responses = CRUDHandsardWebsiteResponse(session).get_all_by_report_type(report_type)

    failing, passing = [], []
    for response in responses:
        report = build_report(response)
        if report.markdown_content is None:
            continue
        start = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            response.report_type,
        )
        if start is None:
            failing.append((response, report))
        else:
            passing.append((response, report))

    print(f"\n{'='*60}")
    print(f"report_type={report_type!r}: {len(failing)} failing, {len(passing)} passing (of those with markdown)")

    print(f"\n--- FAILING (showing {min(max_failing, len(failing))}) ---")
    for response, report in failing[:max_failing]:
        show_doc(response, report)

    print(f"\n--- PASSING (showing {min(max_passing, len(passing))}) ---")
    for response, report in passing[:max_passing]:
        show_doc(response, report)


if __name__ == "__main__":
    types = sys.argv[1:] if len(sys.argv) > 1 else ["bill-intro", "budget", "president-address", "atbp"]
    with Session(engine) as session:
        for report_type in types:
            inspect_type(session, report_type)
