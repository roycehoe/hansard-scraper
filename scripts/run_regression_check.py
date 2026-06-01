"""
Regression check for the speech → speaker resolution pipeline.

Loads the regression Speech IDs from docs/speech-speaker/sample.json and applies
the same preprocessing + resolution logic as _populate_speech_speaker_ids in
populate/speaker_links.py — but in-memory only, no DB writes.

Reports per-speech pass/fail and an overall count to compare against the
last-documented regression baseline (40/40 at iteration 6).

Usage:
    PYTHONPATH=. poetry run python3 scripts/run_regression_check.py
"""
import json
import re
from pathlib import Path

from sqlmodel import Session

from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from database.init import engine
from services.attendance import (
    SpeakerLookups,
    build_speaker_lookups,
    normalize_name,
    resolve_canonical_name,
    strip_title,
)

_SAMPLE_PATH = Path(__file__).parent.parent / "docs" / "speech-speaker" / "sample.json"
_COLONIAL_PARLIAMENT_FALLBACKS = [1, 2, 3]
_NON_SPEAKERS = {
    "An hon. Member", "Some hon. Members", "Non-Residents",
    "Tributes by Leader of the House and Opposition Leaders",
}


def _resolve(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> tuple[str | None, int]:
    canonical = resolve_canonical_name(name, parliament, lookups)
    if canonical is not None or parliament != 0:
        return canonical, parliament
    for fallback in _COLONIAL_PARLIAMENT_FALLBACKS:
        candidate = resolve_canonical_name(name, fallback, lookups)
        if candidate and (candidate, fallback) in speaker_id_lookup:
            return candidate, fallback
    return None, parliament


def _preprocess(speaker: str) -> str | None:
    if speaker in _NON_SPEAKERS or speaker.startswith("(") or speaker.startswith("_"):
        return None
    raw = speaker.rstrip(":").strip()
    paren_match = re.search(r"\s*\(([^)]+)\)\s*$", raw)
    if paren_match:
        inner = paren_match.group(1).strip()
        if strip_title(inner) != inner:
            raw = inner
        else:
            raw = raw[: paren_match.start()]
    raw = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", raw)
    name = normalize_name(strip_title(raw))
    return name or None


def main() -> None:
    sample = json.loads(_SAMPLE_PATH.read_text())
    regression_ids: list[int] = sample["regression"]

    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        rows = CRUDSpeech(session).get_speaker_info_by_ids(regression_ids)

    speaker_id_lookup: dict[tuple[str, int], int] = {
        (s.name, s.parliament_number): s.id for s in speakers if s.id is not None
    }
    lookups = build_speaker_lookups(speakers)

    rows_by_id = {speech_id: (speaker, parliament) for speech_id, speaker, parliament in rows}

    passed = 0
    failed: list[tuple[int, str, int, str | None]] = []

    for speech_id in regression_ids:
        if speech_id not in rows_by_id:
            failed.append((speech_id, "<missing>", 0, None))
            continue
        speaker, parliament = rows_by_id[speech_id]
        if not speaker:
            failed.append((speech_id, "<null speaker>", parliament, None))
            continue

        name = _preprocess(speaker)
        if not name:
            failed.append((speech_id, speaker, parliament, None))
            continue

        canonical, resolved_parliament = _resolve(name, parliament, lookups, speaker_id_lookup)
        speaker_id = speaker_id_lookup.get((canonical, resolved_parliament)) if canonical else None

        if speaker_id:
            passed += 1
        else:
            failed.append((speech_id, speaker, parliament, canonical))

    total = len(regression_ids)
    print(f"\nRegression set: {passed}/{total} passing")
    print("Baseline (iteration 6): 40/40\n")

    if failed:
        print(f"{'ID':>8}  {'parl':>4}  {'speaker':<50}  {'canonical'}")
        print("-" * 100)
        for speech_id, speaker, parliament, canonical in failed:
            print(f"{speech_id:>8}  {parliament:>4}  {speaker:<50}  {canonical or '<unresolved>'}")
    else:
        print("No regressions — all 40 speeches still resolve.")


if __name__ == "__main__":
    main()
