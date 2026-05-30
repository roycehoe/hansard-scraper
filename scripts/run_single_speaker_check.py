"""
Run get_speeches against all single-speaker docs (MPs Speaking == 1 name)
and report how many now yield a speech vs still return [].
"""
from collections import defaultdict

from sqlmodel import Session

from crud.report import CRUDReport
from database.init import engine
from services.speech import (
    _extract_mps_speaking,
    get_speeches,
    get_start_of_speech_line,
)


def run():
    with Session(engine) as session:
        reports = CRUDReport(session).get_all_with_markdown()

    single_speaker = [
        r for r in reports
        if len(_extract_mps_speaking(r.markdown_content)) == 1
    ]
    print(f"Single-speaker docs: {len(single_speaker)}")

    passed_by_type: dict[str, int] = defaultdict(int)
    failed_by_type: dict[str, int] = defaultdict(int)
    no_start_by_type: dict[str, int] = defaultdict(int)

    for report in single_speaker:
        start_line = get_start_of_speech_line(
            report.markdown_content,
            report.title,
            report.subtitle,
            report.original_title,
            report.report_type,
        )
        if start_line is None:
            no_start_by_type[report.report_type] += 1
            continue
        speeches = get_speeches(report.markdown_content, start_line)
        if speeches:
            passed_by_type[report.report_type] += 1
        else:
            failed_by_type[report.report_type] += 1

    all_types = sorted(
        set(list(passed_by_type) + list(failed_by_type) + list(no_start_by_type))
    )

    total_passed = sum(passed_by_type.values())
    total_failed = sum(failed_by_type.values())
    total_no_start = sum(no_start_by_type.values())

    print(f"\n{'report_type':<28} {'pass':>6} {'fail':>6} {'no_start':>9}")
    print("-" * 52)
    for rt in all_types:
        p = passed_by_type.get(rt, 0)
        f = failed_by_type.get(rt, 0)
        ns = no_start_by_type.get(rt, 0)
        print(f"{rt:<28} {p:>6} {f:>6} {ns:>9}")
    print("-" * 52)
    print(f"{'TOTAL':<28} {total_passed:>6} {total_failed:>6} {total_no_start:>9}")
    print()
    total = total_passed + total_failed + total_no_start
    pct = 100 * total_passed / total if total else 0
    print(f"Pass rate (of {total}): {pct:.1f}%")
    if total_failed:
        print(f"  {total_failed} still fail — empty body after start line")


if __name__ == "__main__":
    run()
