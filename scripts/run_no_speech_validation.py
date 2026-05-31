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

from crud.report import CRUDReport
from database.init import engine
from database.report import Report
from services.speech import get_speeches, get_start_of_speech_line

BOLD_SPEAKER_RE = re.compile(r"\*\*[^* ][^*]*\*\*")
K = 5
SEED = 42


def run():
    random.seed(SEED)

    with Session(engine) as session:
        reports = CRUDReport(session).get_all_with_markdown()

    print(f"Reports with markdown: {len(reports)}")

    no_speech_by_type: dict[str, list[tuple[Report, int]]] = defaultdict(list)
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
            continue
        total_with_start += 1
        if not get_speeches(report.markdown_content, start_line, report.report_type):
            no_speech_by_type[report.report_type].append((report, start_line))

    total_no_speech = sum(len(v) for v in no_speech_by_type.values())
    print(f"With start line:       {total_with_start}")
    print(f"No-speech docs:        {total_no_speech}")
    print()

    print("Breakdown by report_type:")
    for rt, items in sorted(no_speech_by_type.items(), key=lambda x: -len(x[1])):
        print(f"  {rt:<30} {len(items)}")
    print()

    print("=" * 80)
    print("VALIDATION SAMPLE")
    print("=" * 80)

    total_checked = 0
    suspicious = []

    for rt, items in sorted(no_speech_by_type.items(), key=lambda x: -len(x[1])):
        sample = random.sample(items, min(K, len(items)))
        print(f"\n--- {rt} ({len(items)} total, checking {len(sample)}) ---")

        for report, start_line in sample:
            total_checked += 1
            lines_after = report.markdown_content.splitlines()[start_line + 1 :]

            bold_lines = [line for line in lines_after if BOLD_SPEAKER_RE.search(line.strip())]
            status = "SUSPICIOUS" if bold_lines else "OK"
            if bold_lines:
                suspicious.append((report, start_line, bold_lines))

            title_display = report.title[:60] if report.title else ""
            print(f"  [{status}] id={report.id}  parl={report.parliament_number}  {title_display!r}")
            print(f"          start_line={start_line}  lines_after={len(lines_after)}")

            for i, line in enumerate(lines_after[:20]):
                marker = "  <-- BOLD" if BOLD_SPEAKER_RE.search(line.strip()) else ""
                print(f"    {start_line + 1 + i:4d}: {line[:100]}{marker}")
            if len(lines_after) > 20:
                print(f"    ... ({len(lines_after) - 20} more lines)")
            print()

    print("=" * 80)
    print(f"Checked:                   {total_checked}")
    print(f"Suspicious (bold found):   {len(suspicious)}")
    print(f"Confirmed no-speaker:      {total_checked - len(suspicious)}")

    if suspicious:
        print()
        print("=== SUSPICIOUS DOCS (bold speaker pattern present but no speeches) ===")
        for report, start_line, bold_lines in suspicious:
            print(f"\n  id={report.id}  type={report.report_type}  parl={report.parliament_number}")
            print(f"  title: {report.title!r}")
            print(f"  bold lines found after start_line={start_line}:")
            for bl in bold_lines[:5]:
                print(f"    {bl[:120]}")


if __name__ == "__main__":
    run()
