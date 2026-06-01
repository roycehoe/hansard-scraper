"""
Baseline assessment: what fraction of Speech.speaker values resolve to an Mp row?

Usage:
    poetry run python3 scripts/speech_speaker_match_rate.py

Samples ~200 Speech rows stratified by report_type, applies the MP name matching
pipeline, and reports the match rate overall and by report_type. Top unmatched
speaker strings are printed to guide any follow-up curation.
"""
import random
from collections import Counter, defaultdict

from sqlmodel import Session

from crud.mp import CRUDMp
from crud.speech import CRUDSpeech
from database.init import engine
from services.sitting_attendance import (
    build_mp_lookups,
    normalize_name,
    resolve_canonical_name,
    strip_title,
)

SAMPLE_PER_TYPE = 10
SEED = 42
TOP_UNMATCHED = 30

# (speaker, report_type, parliament_number) namedtuple-like
_Row = tuple[str, str, int]


def main():
    random.seed(SEED)

    with Session(engine) as session:
        mps = CRUDMp(session).get_all()
        all_rows: list[_Row] = CRUDSpeech(session).get_speakers_with_report_type()

    mp_id_lookup: dict[tuple[str, int], int] = {
        (mp.name, mp.parliament_number): mp.id
        for mp in mps
        if mp.id is not None
    }
    lookups = build_mp_lookups(mps)

    # Stratify by report_type
    by_type: dict[str, list[_Row]] = defaultdict(list)
    for row in all_rows:
        by_type[row[1]].append(row)

    sample: list[_Row] = []
    for report_type, items in by_type.items():
        k = min(SAMPLE_PER_TYPE, len(items))
        sample.extend(random.sample(items, k))

    # Run matching
    matched = 0
    unmatched_by_type: dict[str, list[str]] = defaultdict(list)
    type_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"matched": 0, "total": 0})

    for speaker, report_type, parliament in sample:
        name = strip_title(speaker.rstrip(":").strip())
        name = normalize_name(name)
        canonical = resolve_canonical_name(name, parliament, lookups) if name else None
        found = canonical is not None and (canonical, parliament) in mp_id_lookup

        type_stats[report_type]["total"] += 1
        if found:
            matched += 1
            type_stats[report_type]["matched"] += 1
        else:
            unmatched_by_type[report_type].append(speaker)

    total = len(sample)
    print(f"\nOverall: {matched}/{total} = {matched/total*100:.1f}%\n")
    print(f"{'Report type':<30} {'Matched':>8} {'Total':>7} {'Rate':>7}")
    print("-" * 56)
    for rt, stats in sorted(type_stats.items()):
        m, t = stats["matched"], stats["total"]
        rate = m / t * 100 if t else 0
        print(f"{rt:<30} {m:>8} {t:>7} {rate:>6.1f}%")

    all_unmatched = [s for speakers in unmatched_by_type.values() for s in speakers]
    top = Counter(all_unmatched).most_common(TOP_UNMATCHED)
    print(f"\nTop {TOP_UNMATCHED} unmatched speaker strings:")
    for speaker, count in top:
        print(f"  {count:>3}x  {speaker!r}")


if __name__ == "__main__":
    main()
