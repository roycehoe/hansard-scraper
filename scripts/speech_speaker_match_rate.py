import random
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechReportTypeRow
from database.init import engine
from logs import logger
from services.attendance import build_speaker_lookups
from utils.names import (
    normalize_name,
    strip_title,
)
from utils.speaker_resolution import resolve_canonical_name

_SAMPLE_PER_TYPE = 10
_SEED = 42
_TOP_UNMATCHED = 30
_PERCENT = 100
_SEPARATOR_WIDTH = 56


@dataclass
class _MatchStats:
    matched: int = 0
    total: int = 0


def speech_speaker_match_rate() -> None:
    random.seed(_SEED)

    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        all_rows: list[SpeechReportTypeRow] = CRUDSpeech(session).get_report_type_rows_by_speaker_not_null()

    name_parliament_number_to_speaker_id: dict[tuple[str, int], int] = {
        (speaker.name, speaker.parliament_number): speaker.id
        for speaker in speakers
        if speaker.id is not None
    }
    lookups = build_speaker_lookups(speakers)

    report_type_to_speech_rows: dict[str, list[SpeechReportTypeRow]] = defaultdict(list)
    for speech_row in all_rows:
        report_type_to_speech_rows[speech_row.report_type].append(speech_row)

    sample: list[SpeechReportTypeRow] = []
    for report_type, report_type_speech_rows in report_type_to_speech_rows.items():
        sample_size = min(_SAMPLE_PER_TYPE, len(report_type_speech_rows))
        sample.extend(random.sample(report_type_speech_rows, sample_size))

    matched = 0
    report_type_to_unmatched_speakers: dict[str, list[str]] = defaultdict(list)
    report_type_to_stats: dict[str, _MatchStats] = defaultdict(_MatchStats)

    for speech_row in sample:
        name = strip_title(speech_row.speaker.rstrip(":").strip())
        name = normalize_name(name)
        canonical_name = resolve_canonical_name(name, speech_row.parliament_number, lookups) if name else None
        is_found = canonical_name is not None and (canonical_name, speech_row.parliament_number) in name_parliament_number_to_speaker_id

        report_type_to_stats[speech_row.report_type].total += 1
        if is_found:
            matched += 1
            report_type_to_stats[speech_row.report_type].matched += 1
        else:
            report_type_to_unmatched_speakers[speech_row.report_type].append(speech_row.speaker)

    total = len(sample)
    logger.info(f"\nOverall: {matched}/{total} = {matched/total*_PERCENT:.1f}%\n")
    logger.info(f"{'Report type':<30} {'Matched':>8} {'Total':>7} {'Rate':>7}")
    logger.info("-" * _SEPARATOR_WIDTH)
    for report_type, stats in sorted(report_type_to_stats.items()):
        matched_count, total_count = stats.matched, stats.total
        rate = matched_count / total_count * _PERCENT if total_count else 0
        logger.info(f"{report_type:<30} {matched_count:>8} {total_count:>7} {rate:>6.1f}%")

    all_unmatched = [unmatched_speaker for unmatched_speakers in report_type_to_unmatched_speakers.values() for unmatched_speaker in unmatched_speakers]
    top = Counter(all_unmatched).most_common(_TOP_UNMATCHED)
    logger.info(f"\nTop {_TOP_UNMATCHED} unmatched speaker strings:")
    for speaker, count in top:
        logger.info(f"  {count:>3}x  {speaker!r}")


if __name__ == "__main__":
    speech_speaker_match_rate()
