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

_TABLE_WIDTH = 52


def run() -> None:
    with Session(engine) as session:
        reports = CRUDReport(session).get_by_markdown_content_not_null()

    single_speaker = [
        report for report in reports
        if len(_extract_mps_speaking(report.markdown_content)) == 1
    ]
    print(f"Single-speaker docs: {len(single_speaker)}")

    report_type_to_passed_count: dict[str, int] = defaultdict(int)
    report_type_to_failed_count: dict[str, int] = defaultdict(int)
    report_type_to_no_start_count: dict[str, int] = defaultdict(int)

    for report in single_speaker:
        start_line = get_start_of_speech_line(
            report.markdown_content,
            report.title,
            report.subtitle,
            report.original_title,
            report.report_type,
        )
        if start_line is None:
            report_type_to_no_start_count[report.report_type] += 1
            continue
        speeches = get_speeches(report.markdown_content, start_line, report.report_type)
        if speeches:
            report_type_to_passed_count[report.report_type] += 1
        else:
            report_type_to_failed_count[report.report_type] += 1

    all_types = sorted(
        set(list(report_type_to_passed_count) + list(report_type_to_failed_count) + list(report_type_to_no_start_count))
    )

    total_passed = sum(report_type_to_passed_count.values())
    total_failed = sum(report_type_to_failed_count.values())
    total_no_start = sum(report_type_to_no_start_count.values())

    print(f"\n{'report_type':<28} {'pass':>6} {'fail':>6} {'no_start':>9}")
    print("-" * _TABLE_WIDTH)
    for report_type in all_types:
        passed = report_type_to_passed_count.get(report_type, 0)
        failed = report_type_to_failed_count.get(report_type, 0)
        no_start = report_type_to_no_start_count.get(report_type, 0)
        print(f"{report_type:<28} {passed:>6} {failed:>6} {no_start:>9}")
    print("-" * _TABLE_WIDTH)
    print(f"{'TOTAL':<28} {total_passed:>6} {total_failed:>6} {total_no_start:>9}")
    print()
    total = total_passed + total_failed + total_no_start
    percentage = 100 * total_passed / total if total else 0
    print(f"Pass rate (of {total}): {percentage:.1f}%")
    if total_failed:
        print(f"  {total_failed} still fail — empty body after start line")


if __name__ == "__main__":
    run()
