"""Diagnostic script for the speech parsing refine loop."""

import random
from collections import defaultdict

from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from database.init import engine
from services.report import build_report
from services.speech import get_speeches, get_start_of_speech_line


def get_report_type_speech_stats(session: Session) -> dict:
    """For each report_type, count how many responses have markdown and how many yield speeches."""
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    stats = defaultdict(lambda: {"total": 0, "has_markdown": 0, "has_start_line": 0, "can_get_speeches": 0})

    for response in responses:
        report_type = response.report_type
        stats[report_type]["total"] += 1
        report = build_report(response)
        if report.markdown_content is None:
            continue
        stats[report_type]["has_markdown"] += 1
        start = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            response.report_type,
        )
        if start is None:
            continue
        stats[report_type]["has_start_line"] += 1
        try:
            get_speeches(report.markdown_content, start)
            stats[report_type]["can_get_speeches"] += 1
        except Exception:
            pass

    return dict(stats)


def get_failing_sample(session: Session, no_speech_types: set[str], k: int = 3) -> dict:
    """Sample up to k failing documents per (failure_stage, report_type) group."""
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    groups = defaultdict(list)

    for response in responses:
        if response.report_type in no_speech_types:
            continue
        report = build_report(response)
        if report.markdown_content is None:
            continue
        start = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            response.report_type,
        )
        if start is None:
            groups[("has_start_line", response.report_type)].append(response)
            continue
        try:
            get_speeches(report.markdown_content, start)
        except Exception:
            groups[("can_get_speeches", response.report_type)].append(response)

    sample = {}
    for key, items in groups.items():
        random.shuffle(items)
        sample[key] = items[:k]
    return sample


def get_passing_sample(session: Session, no_speech_types: set[str], n: int = 30) -> list:
    """Sample n currently-passing documents for regression testing."""
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    passing = []

    for response in responses:
        if response.report_type in no_speech_types:
            continue
        report = build_report(response)
        if report.markdown_content is None:
            continue
        start = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            response.report_type,
        )
        if start is None:
            continue
        try:
            get_speeches(report.markdown_content, start)
            passing.append(response)
        except Exception:
            pass

    random.shuffle(passing)
    return passing[:n]


def run_stats_on(responses: list) -> dict:
    """Run _get_statistics equivalent on a list of responses, return counts."""
    results = {"pass": [], "fail_start_line": [], "fail_speeches": []}
    for response in responses:
        report = build_report(response)
        if report.markdown_content is None:
            continue
        start = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            response.report_type,
        )
        if start is None:
            results["fail_start_line"].append(response.id)
            continue
        try:
            get_speeches(report.markdown_content, start)
            results["pass"].append(response.id)
        except Exception:
            results["fail_speeches"].append(response.id)
    return results


if __name__ == "__main__":
    with Session(engine) as session:
        crud = CRUDHandsardWebsiteResponse(session)
        print("=== Setup: report_type speech stats ===")
        stats = get_report_type_speech_stats(session)
        no_speech_types = set()
        for report_type, s in sorted(stats.items(), key=lambda x: x[1]["has_markdown"], reverse=True):
            has_markdown = s["has_markdown"]
            has_start_line = s["has_start_line"]
            can_get_speeches = s["can_get_speeches"]
            if has_markdown > 0 and can_get_speeches == 0:
                no_speech_types.add(report_type)
                marker = " <-- ZERO SPEECHES"
            else:
                marker = ""
            print(f"  {report_type:30s} total={s['total']:4d} has_md={has_markdown:4d} has_start={has_start_line:4d} speeches={can_get_speeches:4d}{marker}")

        print(f"\nNo-speech report types (excluded from target): {no_speech_types}")

        print("\n=== Baseline (excluding no-speech types) ===")
        all_responses = crud.get_all()
        target_with_md = [
            response for response in all_responses
            if response.report_type not in no_speech_types and build_report(response).markdown_content is not None
        ]
        baseline = run_stats_on(target_with_md)
        total = len(baseline["pass"]) + len(baseline["fail_start_line"]) + len(baseline["fail_speeches"])
        pct = 100 * len(baseline["pass"]) / total if total else 0
        print(f"  Pass: {len(baseline['pass'])}/{total} ({pct:.1f}%)")
        print(f"  Fail has_start_line: {len(baseline['fail_start_line'])}")
        print(f"  Fail can_get_speeches: {len(baseline['fail_speeches'])}")
