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

_SAMPLE_PER_TYPE = 10
_SEED = 42
_TOP_UNMATCHED = 30
_PERCENT = 100
_SEPARATOR_WIDTH = 56


def main():
    random.seed(_SEED)

    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        all_rows: list[SpeechReportTypeRow] = CRUDSpeech(session).get_speaker_rows_by_speaker_not_null()

    name_and_parliament_to_speaker_id: dict[tuple[str, int], int] = {
        (speaker.name, speaker.parliament_number): speaker.id
        for speaker in speakers
        if speaker.id is not None
    }
    lookups = build_speaker_lookups(speakers)

    # Stratify by report_type
    report_type_to_rows: dict[str, list[SpeechReportTypeRow]] = defaultdict(list)
    for row in all_rows:
        report_type_to_rows[row.report_type].append(row)

    sample: list[SpeechReportTypeRow] = []
    for report_type, items in report_type_to_rows.items():
        sample_size = min(_SAMPLE_PER_TYPE, len(items))
        sample.extend(random.sample(items, sample_size))

    # Run matching
    matched = 0
    report_type_to_unmatched_speakers: dict[str, list[str]] = defaultdict(list)
    report_type_to_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"matched": 0, "total": 0})

    for row in sample:
        name = strip_title(row.speaker.rstrip(":").strip())
        name = normalize_name(name)
        canonical = resolve_canonical_name(name, row.parliament_number, lookups) if name else None
        is_found = canonical is not None and (canonical, row.parliament_number) in name_and_parliament_to_speaker_id

        report_type_to_stats[row.report_type]["total"] += 1
        if is_found:
            matched += 1
            report_type_to_stats[row.report_type]["matched"] += 1
        else:
            report_type_to_unmatched_speakers[row.report_type].append(row.speaker)

    total = len(sample)
    print(f"\nOverall: {matched}/{total} = {matched/total*_PERCENT:.1f}%\n")
    print(f"{'Report type':<30} {'Matched':>8} {'Total':>7} {'Rate':>7}")
    print("-" * _SEPARATOR_WIDTH)
    for report_type, stats in sorted(report_type_to_stats.items()):
        matched_count, total_count = stats["matched"], stats["total"]
        rate = matched_count / total_count * _PERCENT if total_count else 0
        print(f"{report_type:<30} {matched_count:>8} {total_count:>7} {rate:>6.1f}%")

    all_unmatched = [unmatched_speaker for unmatched_speakers in report_type_to_unmatched_speakers.values() for unmatched_speaker in unmatched_speakers]
    top = Counter(all_unmatched).most_common(_TOP_UNMATCHED)
    print(f"\nTop {_TOP_UNMATCHED} unmatched speaker strings:")
    for speaker, count in top:
        print(f"  {count:>3}x  {speaker!r}")


if __name__ == "__main__":
    main()
