"""
Baseline assessment: what fraction of Speech.speaker values resolve to a Speaker row?

Usage:
    poetry run python3 scripts/speech_speaker_match_rate.py

Samples ~200 Speech rows stratified by report_type, applies the speaker name matching
pipeline, and reports the match rate overall and by report_type. Top unmatched
speaker strings are printed to guide any follow-up curation.
"""
import random
from collections import Counter, defaultdict

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechReportTypeRow
from database.init import engine
from services.attendance import (
    build_speaker_lookups,
    resolve_canonical_name,
)
from utils.names import (
    normalize_name,
    strip_title,
)

SAMPLE_PER_TYPE = 10
SEED = 42
TOP_UNMATCHED = 30


def main():
    random.seed(SEED)

    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        all_rows: list[SpeechReportTypeRow] = CRUDSpeech(session).get_speakers_with_report_type()

    speaker_id_lookup: dict[tuple[str, int], int] = {
        (s.name, s.parliament_number): s.id
        for s in speakers
        if s.id is not None
    }
    lookups = build_speaker_lookups(speakers)

    # Stratify by report_type
    by_type: dict[str, list[SpeechReportTypeRow]] = defaultdict(list)
    for row in all_rows:
        by_type[row.report_type].append(row)

    sample: list[SpeechReportTypeRow] = []
    for report_type, items in by_type.items():
        k = min(SAMPLE_PER_TYPE, len(items))
        sample.extend(random.sample(items, k))

    # Run matching
    matched = 0
    unmatched_by_type: dict[str, list[str]] = defaultdict(list)
    type_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"matched": 0, "total": 0})

    for row in sample:
        name = strip_title(row.speaker.rstrip(":").strip())
        name = normalize_name(name)
        canonical = resolve_canonical_name(name, row.parliament_number, lookups) if name else None
        found = canonical is not None and (canonical, row.parliament_number) in speaker_id_lookup

        type_stats[row.report_type]["total"] += 1
        if found:
            matched += 1
            type_stats[row.report_type]["matched"] += 1
        else:
            unmatched_by_type[row.report_type].append(row.speaker)

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
