"""
Expand the stratified sample to cover parliament=0 speeches newly matchable
after the colonial LA members load (iteration 13).

Adds K=5 pilot + K=3 held-out per report_type for parliament=0 speeches not
already in the sample. Expands the regression set proportionally (~1:5 ratio)
from new pilot speeches that currently resolve.

Updates docs/speech-speaker/sample.json in-place.

Usage:
    PYTHONPATH=. poetry run python3 scripts/expand_sample.py

Run once — re-running is safe (no eligible speeches remain after first run).
"""
import json
import random
import re
from collections import defaultdict
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

_SAMPLE_PATH = Path(__file__).parent.parent / "docs" / "speech-mp" / "sample.json"
_SEED = 42
_K_PILOT = 5
_K_HELD_OUT = 3
_COLONIAL_PARLIAMENT_FALLBACKS = [1, 2, 3]

_STRUCTURAL_EXCLUSIONS = {
    "An hon. Member", "Some hon. Members", "Non-Residents",
    "Tributes by Leader of the House and Opposition Leaders",
    "Mr Speaker", "Mr Deputy Speaker", "The Clerk", "Hon. Members",
    "Several Members", "Members",
}
_SECTION_HEADER_RE = re.compile(r"^[A-Z][A-Z0-9 /(),.\-]+$")


def _is_excluded(speaker: str) -> bool:
    if speaker in _STRUCTURAL_EXCLUSIONS:
        return True
    if speaker.startswith("Mr Deputy Speaker (") or speaker.startswith("The Deputy Speaker ("):
        return True
    if _SECTION_HEADER_RE.match(speaker):
        return True
    return False


def _preprocess(speaker: str) -> str | None:
    if _is_excluded(speaker) or speaker.startswith("(") or speaker.startswith("_"):
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


def _resolves(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> bool:
    canonical = resolve_canonical_name(name, parliament, lookups)
    if canonical is not None:
        return (canonical, parliament) in speaker_id_lookup
    if parliament == 0:
        for fallback in _COLONIAL_PARLIAMENT_FALLBACKS:
            candidate = resolve_canonical_name(name, fallback, lookups)
            if candidate and (candidate, fallback) in speaker_id_lookup:
                return True
    return False


def main() -> None:
    random.seed(_SEED)

    sample = json.loads(_SAMPLE_PATH.read_text())
    existing_ids = set(sample["pilot"] + sample["held_out"] + sample["regression"])

    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        rows = CRUDSpeech(session).get_speaker_info_for_parliament(0)

    speaker_id_lookup = {(s.name, s.parliament_number): s.id for s in speakers if s.id is not None}
    lookups = build_speaker_lookups(speakers)

    # Filter: exclude structural non-MPs, artifacts, already-sampled IDs
    eligible: list[tuple[int, str, str, int]] = []
    for speech_id, speaker, report_type, parliament in rows:
        if not speaker:
            continue
        if speech_id in existing_ids:
            continue
        if _is_excluded(speaker) or speaker.startswith("(") or speaker.startswith("_"):
            continue
        eligible.append((speech_id, speaker, report_type, parliament))

    eligible_by_id = {r[0]: r for r in eligible}

    # Group by report_type and sample
    by_type: dict[str, list[tuple[int, str, str, int]]] = defaultdict(list)
    for row in eligible:
        by_type[row[2]].append(row)

    new_pilot: list[int] = []
    new_held_out: list[int] = []

    print(f"Eligible parliament=0 speeches (excluding existing sample): {len(eligible)}")
    print("\nSampling per report_type:")
    for report_type, items in sorted(by_type.items()):
        random.shuffle(items)
        pilot_slice = items[:_K_PILOT]
        held_out_slice = items[_K_PILOT : _K_PILOT + _K_HELD_OUT]
        new_pilot.extend(r[0] for r in pilot_slice)
        new_held_out.extend(r[0] for r in held_out_slice)
        print(f"  {report_type:<30} {len(pilot_slice)} pilot + {len(held_out_slice)} held-out")

    # Regression expansion: run resolution on new pilot speeches
    passing_pilot: list[int] = []
    for speech_id in new_pilot:
        if speech_id not in eligible_by_id:
            continue
        _, speaker, _, parliament = eligible_by_id[speech_id]
        name = _preprocess(speaker)
        if name and _resolves(name, parliament, lookups, speaker_id_lookup):
            passing_pilot.append(speech_id)

    # Maintain ~1:5 regression:pilot ratio (current: 40/202 ≈ 1:5)
    n_regression = max(1, len(new_pilot) // 5)
    new_regression = random.sample(passing_pilot, min(n_regression, len(passing_pilot)))

    sample["pilot"].extend(new_pilot)
    sample["held_out"].extend(new_held_out)
    sample["regression"].extend(new_regression)

    _SAMPLE_PATH.write_text(json.dumps(sample, indent=2))

    print("\nExpansion summary:")
    print(f"  Added pilot:      {len(new_pilot)}")
    print(f"  Added held-out:   {len(new_held_out)}")
    print(f"  Added regression: {len(new_regression)} (from {len(passing_pilot)} passing new pilot)")
    print(f"  New totals — pilot: {len(sample['pilot'])}, held_out: {len(sample['held_out'])}, regression: {len(sample['regression'])}")


if __name__ == "__main__":
    main()
