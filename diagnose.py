"""Diagnostic script for the speech parsing refine loop."""

import random
from collections import defaultdict

from sqlmodel import Session, select

from database.init import engine
from database.report import HandsardWebsiteResponse
from services.report import get_db_report_in
from services.speech import get_speeches, get_start_of_speech_line


def get_report_type_speech_stats(session: Session) -> dict:
    """For each report_type, count how many responses have markdown and how many yield speeches."""
    responses = list(session.exec(select(HandsardWebsiteResponse)).all())
    stats = defaultdict(lambda: {"total": 0, "has_markdown": 0, "has_start_line": 0, "can_get_speeches": 0})

    for resp in responses:
        rt = resp.report_type
        stats[rt]["total"] += 1
        report = get_db_report_in(resp)
        if report.markdown_content is None:
            continue
        stats[rt]["has_markdown"] += 1
        start = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            resp.report_type,
        )
        if start is None:
            continue
        stats[rt]["has_start_line"] += 1
        try:
            get_speeches(report.markdown_content, start)
            stats[rt]["can_get_speeches"] += 1
        except Exception:
            pass

    return dict(stats)


def get_failing_sample(session: Session, no_speech_types: set[str], k: int = 3) -> dict:
    """Sample up to k failing documents per (failure_stage, report_type) group."""
    responses = list(session.exec(select(HandsardWebsiteResponse)).all())
    groups = defaultdict(list)

    for resp in responses:
        if resp.report_type in no_speech_types:
            continue
        report = get_db_report_in(resp)
        if report.markdown_content is None:
            continue
        start = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            resp.report_type,
        )
        if start is None:
            groups[("has_start_line", resp.report_type)].append(resp)
            continue
        try:
            get_speeches(report.markdown_content, start)
        except Exception:
            groups[("can_get_speeches", resp.report_type)].append(resp)

    sample = {}
    for key, items in groups.items():
        random.shuffle(items)
        sample[key] = items[:k]
    return sample


def get_passing_sample(session: Session, no_speech_types: set[str], n: int = 30) -> list:
    """Sample n currently-passing documents for regression testing."""
    responses = list(session.exec(select(HandsardWebsiteResponse)).all())
    passing = []

    for resp in responses:
        if resp.report_type in no_speech_types:
            continue
        report = get_db_report_in(resp)
        if report.markdown_content is None:
            continue
        start = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            resp.report_type,
        )
        if start is None:
            continue
        try:
            get_speeches(report.markdown_content, start)
            passing.append(resp)
        except Exception:
            pass

    random.shuffle(passing)
    return passing[:n]


def run_stats_on(responses: list, label: str = "") -> dict:
    """Run _get_statistics equivalent on a list of responses, return counts."""
    results = {"pass": [], "fail_start_line": [], "fail_speeches": []}
    for resp in responses:
        report = get_db_report_in(resp)
        if report.markdown_content is None:
            continue
        start = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            resp.report_type,
        )
        if start is None:
            results["fail_start_line"].append(resp.id)
            continue
        try:
            get_speeches(report.markdown_content, start)
            results["pass"].append(resp.id)
        except Exception:
            results["fail_speeches"].append(resp.id)
    return results


if __name__ == "__main__":
    with Session(engine) as session:
        print("=== Setup: report_type speech stats ===")
        stats = get_report_type_speech_stats(session)
        no_speech_types = set()
        for rt, s in sorted(stats.items(), key=lambda x: x[1]["has_markdown"], reverse=True):
            has_md = s["has_markdown"]
            has_sl = s["has_start_line"]
            can_sp = s["can_get_speeches"]
            if has_md > 0 and can_sp == 0:
                no_speech_types.add(rt)
                marker = " <-- ZERO SPEECHES"
            else:
                marker = ""
            print(f"  {rt:30s} total={s['total']:4d} has_md={has_md:4d} has_start={has_sl:4d} speeches={can_sp:4d}{marker}")

        print(f"\nNo-speech report types (excluded from target): {no_speech_types}")

        # Baseline: all docs with markdown, excluding no-speech types
        print("\n=== Baseline (excluding no-speech types) ===")
        all_responses = list(session.exec(select(HandsardWebsiteResponse)).all())
        target = [r for r in all_responses if r.report_type not in no_speech_types]
        target_with_md = []
        for r in target:
            rpt = get_db_report_in(r)
            if rpt.markdown_content is not None:
                target_with_md.append(r)

        baseline = run_stats_on(target_with_md, "baseline")
        total = len(baseline["pass"]) + len(baseline["fail_start_line"]) + len(baseline["fail_speeches"])
        pct = 100 * len(baseline["pass"]) / total if total else 0
        print(f"  Pass: {len(baseline['pass'])}/{total} ({pct:.1f}%)")
        print(f"  Fail has_start_line: {len(baseline['fail_start_line'])}")
        print(f"  Fail can_get_speeches: {len(baseline['fail_speeches'])}")
