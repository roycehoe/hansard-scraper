"""Diagnostic script for the speech parsing refine loop."""

import random
from collections import defaultdict
from typing import Optional

from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from database.hansard_website_response import HansardWebsiteResponse
from database.init import engine
from database.report import Report
from services.report import build_report
from services.speech import get_speeches, get_start_of_speech_line


def _get_speech_start(response: HansardWebsiteResponse) -> tuple[Report, Optional[int]]:
    report = build_report(response)
    start = (
        get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            response.report_type,
        )
        if report.markdown_content is not None
        else None
    )
    return report, start


def get_report_type_speech_stats(session: Session) -> dict:
    """For each report_type, count how many responses have markdown and how many yield speeches."""
    responses = CRUDHansardWebsiteResponse(session).get_all()
    report_type_to_counts = defaultdict(lambda: {"total": 0, "has_markdown": 0, "has_start_line": 0, "can_get_speeches": 0})

    for response in responses:
        report_type = response.report_type
        report_type_to_counts[report_type]["total"] += 1
        report, start = _get_speech_start(response)
        if report.markdown_content is None:
            continue
        report_type_to_counts[report_type]["has_markdown"] += 1
        if start is None:
            continue
        report_type_to_counts[report_type]["has_start_line"] += 1
        get_speeches(report.markdown_content, start, response.report_type)
        report_type_to_counts[report_type]["can_get_speeches"] += 1

    return dict(report_type_to_counts)


def get_failing_sample(session: Session, no_speech_types: set[str], sample_size: int = 3) -> dict:
    """Sample up to sample_size failing documents per (failure_stage, report_type) group."""
    responses = CRUDHansardWebsiteResponse(session).get_all()
    stage_and_report_type_to_responses = defaultdict(list)

    for response in responses:
        if response.report_type in no_speech_types:
            continue
        report, start = _get_speech_start(response)
        if report.markdown_content is None:
            continue
        if start is None:
            stage_and_report_type_to_responses[("has_start_line", response.report_type)].append(response)
            continue
        get_speeches(report.markdown_content, start, response.report_type)

    stage_and_report_type_to_sample = {}
    for key, items in stage_and_report_type_to_responses.items():
        random.shuffle(items)
        stage_and_report_type_to_sample[key] = items[:sample_size]
    return stage_and_report_type_to_sample


def get_passing_sample(session: Session, no_speech_types: set[str], sample_size: int = 30) -> list:
    """Sample sample_size currently-passing documents for regression testing."""
    responses = CRUDHansardWebsiteResponse(session).get_all()
    passing = []

    for response in responses:
        if response.report_type in no_speech_types:
            continue
        report, start = _get_speech_start(response)
        if report.markdown_content is None or start is None:
            continue
        try:
            get_speeches(report.markdown_content, start, response.report_type)
            passing.append(response)
        except Exception:  # noqa: BLE001 a corpus survey must record every failing document, not stop at the first
            pass

    random.shuffle(passing)
    return passing[:sample_size]


def run_stats_on(responses: list) -> dict:
    """Run _get_statistics equivalent on a list of responses, return counts."""
    results = {"pass": [], "fail_start_line": [], "fail_speeches": []}
    for response in responses:
        report, start = _get_speech_start(response)
        if report.markdown_content is None:
            continue
        if start is None:
            results["fail_start_line"].append(response.id)
            continue
        get_speeches(report.markdown_content, start, response.report_type)
        results["pass"].append(response.id)
    return results


if __name__ == "__main__":
    with Session(engine) as session:
        crud = CRUDHansardWebsiteResponse(session)
        print("=== Setup: report_type speech stats ===")
        report_type_to_counts = get_report_type_speech_stats(session)
        no_speech_types = set()
        for report_type, speech_statistics in sorted(report_type_to_counts.items(), key=lambda entry: entry[1]["has_markdown"], reverse=True):
            has_markdown = speech_statistics["has_markdown"]
            has_start_line = speech_statistics["has_start_line"]
            can_get_speeches = speech_statistics["can_get_speeches"]
            if has_markdown > 0 and can_get_speeches == 0:
                no_speech_types.add(report_type)
                marker = " <-- ZERO SPEECHES"
            else:
                marker = ""
            print(f"  {report_type:30s} total={speech_statistics['total']:4d} has_md={has_markdown:4d} has_start={has_start_line:4d} speeches={can_get_speeches:4d}{marker}")

        print(f"\nNo-speech report types (excluded from target): {no_speech_types}")

        print("\n=== Baseline (excluding no-speech types) ===")
        all_responses = crud.get_all()
        target_with_markdown = [
            response for response in all_responses
            if response.report_type not in no_speech_types and build_report(response).markdown_content is not None
        ]
        baseline = run_stats_on(target_with_markdown)
        total = len(baseline["pass"]) + len(baseline["fail_start_line"]) + len(baseline["fail_speeches"])
        percentage = 100 * len(baseline["pass"]) / total if total else 0
        print(f"  Pass: {len(baseline['pass'])}/{total} ({percentage:.1f}%)")
        print(f"  Fail has_start_line: {len(baseline['fail_start_line'])}")
        print(f"  Fail can_get_speeches: {len(baseline['fail_speeches'])}")
