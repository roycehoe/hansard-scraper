"""
Validate the no-speech docs: confirm that docs where get_speeches returns []
genuinely have no bold speaker markup after the start line.

Draws a stratified sample (K=5 per report_type) from the Report table,
inspects the markdown after start_line, and flags any doc where a bold
speaker pattern (**Name:**) is present.
"""

import random
import re
from collections import defaultdict

from sqlmodel import Session

import database.speech  # noqa: F401  (registers Speech for Report.speeches)
from crud.report import CRUDReport
from database.init import engine
from database.report import Report
from services.speech import get_speeches, get_start_of_speech_line

_BOLD_SPEAKER_RE = re.compile(r"\*\*[^* ][^*]*\*\*")
_SAMPLE_SIZE_PER_REPORT_TYPE = 5
_SEED = 42
_SEPARATOR_WIDTH = 80
_TITLE_DISPLAY_WIDTH = 60
_PREVIEW_LINE_COUNT = 20
_PREVIEW_LINE_WIDTH = 100
_BOLD_LINE_COUNT = 5
_BOLD_LINE_WIDTH = 120


def run():
    random.seed(_SEED)

    with Session(engine) as session:
        reports = CRUDReport(session).get_by_markdown_content_not_null()

    print(f"Reports with markdown: {len(reports)}")

    report_type_to_no_speech_items: dict[str, list[tuple[Report, int]]] = defaultdict(list)
    no_start_line: list[Report] = []
    total_with_start = 0

    for report in reports:
        start_line = get_start_of_speech_line(
            report.markdown_content,
            report.title,
            report.subtitle,
            report.original_title,
            report.report_type,
        )
        if start_line is None:
            no_start_line.append(report)
            continue
        total_with_start += 1
        if not get_speeches(report.markdown_content, start_line, report.report_type):
            report_type_to_no_speech_items[report.report_type].append((report, start_line))

    total_no_speech = sum(len(items) for items in report_type_to_no_speech_items.values())
    print(f"With start line:       {total_with_start}")
    print(f"No-speech docs:        {total_no_speech}")
    print(f"No start line:         {len(no_start_line)}")
    print()

    print("Breakdown by report_type:")
    for report_type, items in sorted(report_type_to_no_speech_items.items(), key=lambda entry: -len(entry[1])):
        print(f"  {report_type:<30} {len(items)}")
    print()

    print("=" * _SEPARATOR_WIDTH)
    print("VALIDATION SAMPLE")
    print("=" * _SEPARATOR_WIDTH)

    total_checked = 0
    suspicious = []

    for report_type, items in sorted(report_type_to_no_speech_items.items(), key=lambda entry: -len(entry[1])):
        sample = random.sample(items, min(_SAMPLE_SIZE_PER_REPORT_TYPE, len(items)))
        print(f"\n--- {report_type} ({len(items)} total, checking {len(sample)}) ---")

        for report, start_line in sample:
            total_checked += 1
            lines_after = report.markdown_content.splitlines()[start_line + 1 :]

            bold_lines = [line for line in lines_after if _BOLD_SPEAKER_RE.search(line.strip())]
            status = "SUSPICIOUS" if bold_lines else "OK"
            if bold_lines:
                suspicious.append((report, start_line, bold_lines))

            title_display = report.title[:_TITLE_DISPLAY_WIDTH] if report.title else ""
            print(f"  [{status}] id={report.id}  parl={report.parliament_number}  {title_display!r}")
            print(f"          start_line={start_line}  lines_after={len(lines_after)}")

            for offset, line in enumerate(lines_after[:_PREVIEW_LINE_COUNT]):
                marker = "  <-- BOLD" if _BOLD_SPEAKER_RE.search(line.strip()) else ""
                print(f"    {start_line + 1 + offset:4d}: {line[:_PREVIEW_LINE_WIDTH]}{marker}")
            if len(lines_after) > _PREVIEW_LINE_COUNT:
                print(f"    ... ({len(lines_after) - _PREVIEW_LINE_COUNT} more lines)")
            print()

    print("=" * _SEPARATOR_WIDTH)
    print(f"Checked:                   {total_checked}")
    print(f"Suspicious (bold found):   {len(suspicious)}")
    print(f"Confirmed no-speaker:      {total_checked - len(suspicious)}")

    # A report with no start line is never parsed, so it must not drop out of the check unseen.
    print()
    print("=== NO START LINE (never parsed; bold speaker lines counted over the whole doc) ===")
    for report in no_start_line:
        bold_count = sum(1 for line in report.markdown_content.splitlines() if _BOLD_SPEAKER_RE.search(line.strip()))
        status = "SUSPICIOUS" if bold_count else "OK"
        print(f"  [{status}] id={report.id}  type={report.report_type}  parl={report.parliament_number}  "
              f"bold_lines={bold_count}  {report.title[:_TITLE_DISPLAY_WIDTH]!r}")

    if suspicious:
        print()
        print("=== SUSPICIOUS DOCS (bold speaker pattern present but no speeches) ===")
        for report, start_line, bold_lines in suspicious:
            print(f"\n  id={report.id}  type={report.report_type}  parl={report.parliament_number}")
            print(f"  title: {report.title!r}")
            print(f"  bold lines found after start_line={start_line}:")
            for bold_line in bold_lines[:_BOLD_LINE_COUNT]:
                print(f"    {bold_line[:_BOLD_LINE_WIDTH]}")


if __name__ == "__main__":
    run()
