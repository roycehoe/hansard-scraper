"""Manual inspection of failing documents for the refine loop."""

import sys

from sqlmodel import Session, select

from database.handsard_website_response import HandsardWebsiteResponse
from database.init import engine
from services.report import get_db_report_in
from services.speech import get_start_of_speech_line


def show_doc(resp, rpt, max_lines=60):
    start = get_start_of_speech_line(
        rpt.markdown_content, rpt.title, rpt.subtitle, rpt.original_title,
        resp.report_type,
    )
    print(f"  id={resp.id} report_type={resp.report_type!r}")
    print(f"  title={rpt.title!r}")
    print(f"  subtitle={rpt.subtitle!r}")
    print(f"  original_title={rpt.original_title!r}")
    print(f"  has_start_line={start is not None} (line {start})")
    print(f"  markdown ({len(rpt.markdown_content)} chars):")
    for i, line in enumerate(rpt.markdown_content.splitlines()[:max_lines]):
        print(f"    {i:3d}: {line}")
    print()


def inspect_type(session, report_type, max_failing=3, max_passing=2):
    # Filter at SQL level — don't load all rows
    responses = list(
        session.exec(
            select(HandsardWebsiteResponse).where(
                HandsardWebsiteResponse.report_type == report_type
            )
        ).all()
    )

    failing, passing = [], []
    for resp in responses:
        rpt = get_db_report_in(resp)
        if rpt.markdown_content is None:
            continue
        start = get_start_of_speech_line(
            rpt.markdown_content, rpt.title, rpt.subtitle, rpt.original_title,
            resp.report_type,
        )
        if start is None:
            failing.append((resp, rpt))
        else:
            passing.append((resp, rpt))

    print(f"\n{'='*60}")
    print(f"report_type={report_type!r}: {len(failing)} failing, {len(passing)} passing (of those with markdown)")

    print(f"\n--- FAILING (showing {min(max_failing, len(failing))}) ---")
    for resp, rpt in failing[:max_failing]:
        show_doc(resp, rpt)

    print(f"\n--- PASSING (showing {min(max_passing, len(passing))}) ---")
    for resp, rpt in passing[:max_passing]:
        show_doc(resp, rpt)


if __name__ == "__main__":
    types = sys.argv[1:] if len(sys.argv) > 1 else ["bill-intro", "budget", "president-address", "atbp"]
    with Session(engine) as session:
        for rt in types:
            inspect_type(session, rt)
