"""
Baseline assessment: what fraction of Speech.speaker values resolve to an Mp row?

Usage:
    poetry run python3 scripts/speech_speaker_match_rate.py

Samples ~200 Speech rows stratified by report_type, applies the MP name matching
pipeline, and reports the match rate overall and by report_type. Top unmatched
speaker strings are printed to guide any follow-up curation.
"""
import random
from collections import defaultdict

from sqlmodel import select

from database.init import get_session
from database.mp import Mp
from database.report import Report
from database.speech import Speech
from services.sitting_attendance import (
    _normalize_name,
    _strip_title,
    resolve_canonical_name,
)

SAMPLE_PER_TYPE = 10
SEED = 42
TOP_UNMATCHED = 30


def main():
    random.seed(SEED)
    session = next(get_session())

    # Build mp_id lookup: (canonical_name, parliament) → mp_id
    mp_id_lookup: dict[tuple[str, int], int] = {
        (mp.name, mp.parliament_number): mp.id
        for mp in session.exec(select(Mp)).all()
        if mp.id is not None
    }

    # Load all speeches with their report (for parliament_number)
    rows = session.exec(select(Speech, Report).join(Report).where(Speech.speaker != None)).all()  # noqa: E711

    # Stratify by report_type
    by_type: dict[str, list[tuple[Speech, Report]]] = defaultdict(list)
    for speech, report in rows:
        by_type[report.report_type].append((speech, report))

    sample: list[tuple[Speech, Report]] = []
    for report_type, items in by_type.items():
        k = min(SAMPLE_PER_TYPE, len(items))
        sample.extend(random.sample(items, k))

    # Run matching
    matched = 0
    unmatched_by_type: dict[str, list[str]] = defaultdict(list)
    type_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"matched": 0, "total": 0})

    for speech, report in sample:
        parliament = report.parliament_number
        name = _strip_title(speech.speaker.rstrip(":").strip())
        name = _normalize_name(name)
        canonical = resolve_canonical_name(name, parliament) if name else None
        found = canonical is not None and (canonical, parliament) in mp_id_lookup

        type_stats[report.report_type]["total"] += 1
        if found:
            matched += 1
            type_stats[report.report_type]["matched"] += 1
        else:
            unmatched_by_type[report.report_type].append(speech.speaker or "")

    total = len(sample)
    print(f"\nOverall: {matched}/{total} = {matched/total*100:.1f}%\n")
    print(f"{'Report type':<30} {'Matched':>8} {'Total':>7} {'Rate':>7}")
    print("-" * 56)
    for rt, stats in sorted(type_stats.items()):
        m, t = stats["matched"], stats["total"]
        rate = m / t * 100 if t else 0
        print(f"{rt:<30} {m:>8} {t:>7} {rate:>6.1f}%")

    # Collect all unmatched speakers across types for top-N display
    all_unmatched = [s for speakers in unmatched_by_type.values() for s in speakers]
    from collections import Counter
    top = Counter(all_unmatched).most_common(TOP_UNMATCHED)
    print(f"\nTop {TOP_UNMATCHED} unmatched speaker strings:")
    for speaker, count in top:
        print(f"  {count:>3}x  {speaker!r}")


if __name__ == "__main__":
    main()
