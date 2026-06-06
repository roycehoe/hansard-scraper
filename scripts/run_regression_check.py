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
from populate.speaker_resolution_constants import (
    CHIEF_MINISTER_CUTOFF,
    COLONIAL_PARLIAMENT_FALLBACKS,
    NON_SPEAKERS,
    PRESIDING_OFFICERS,
    ROLE_ONLY_SPEAKERS,
)
from services.attendance import (
    SpeakerLookups,
    build_speaker_lookups,
    normalize_name,
    resolve_canonical_name,
    strip_title,
)

_SAMPLE_PATH = Path(__file__).parent.parent / "docs" / "speech-speaker" / "sample.json"


def _get_presiding_officer_role(raw: str) -> str | None:
    if raw in ("Mr Speaker", "Mdm Speaker"):
        return "SPEAKER"
    if raw.startswith("Mr Deputy Speaker") or raw.startswith("The Deputy Speaker"):
        return "DEPUTY SPEAKER"
    return None


def _resolve(
    name: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> tuple[str | None, int]:
    canonical = resolve_canonical_name(name, parliament, lookups)
    if canonical is not None or parliament != 0:
        return canonical, parliament
    for fallback in COLONIAL_PARLIAMENT_FALLBACKS:
        candidate = resolve_canonical_name(name, fallback, lookups)
        if candidate and (candidate, fallback) in speaker_id_lookup:
            return candidate, fallback
    return None, parliament


def _has_title(m: re.Match) -> bool:
    inner = re.sub(r"^(Mr|Mrs|Dr|Ms)\.\s+", r"\1 ", m.group(1).strip())
    return strip_title(inner) != inner


def _preprocess(speaker: str) -> str | None:
    if speaker in NON_SPEAKERS or speaker.startswith("(") or speaker.startswith("_"):
        return None
    raw = speaker.rstrip(":").strip()
    parens = list(re.finditer(r"\(([^)]+)\)", raw))
    if parens:
        title_paren = next(
            (m for m in reversed(parens) if _has_title(m)),
            None,
        )
        if title_paren:
            raw = title_paren.group(1).strip()
        else:
            raw = raw[: parens[0].start()].strip()
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

    rows_by_id = {
        speech_id: (speaker, parliament, sitting_date)
        for speech_id, speaker, parliament, sitting_date in rows
    }

    passed = 0
    failed: list[tuple[int, str, int, str | None]] = []

    for speech_id in regression_ids:
        if speech_id not in rows_by_id:
            failed.append((speech_id, "<missing>", 0, None))
            continue
        speaker, parliament, sitting_date = rows_by_id[speech_id]
        if not speaker:
            failed.append((speech_id, "<null speaker>", parliament, None))
            continue

        raw = speaker.rstrip(":").strip()
        po_role = _get_presiding_officer_role(raw)
        if po_role is not None:
            po_parl = parliament if parliament != 0 else next(
                (p for p in COLONIAL_PARLIAMENT_FALLBACKS if (po_role, p) in PRESIDING_OFFICERS),
                parliament,
            )
            po_name = PRESIDING_OFFICERS.get((po_role, po_parl))
            if po_name:
                po_canonical, po_resolved_parl = _resolve(po_name, po_parl, lookups, speaker_id_lookup)
                po_sid = speaker_id_lookup.get((po_canonical, po_resolved_parl)) if po_canonical else None
                if po_sid:
                    passed += 1
                else:
                    failed.append((speech_id, speaker, parliament, po_canonical))
            else:
                failed.append((speech_id, speaker, parliament, None))
            continue

        # Chief Minister (colonial era): date-based dispatch between Marshall and Lim.
        if raw == "The Chief Minister" and parliament in (0, 1, 2, 3):
            _cm_name = (
                "David Marshall"
                if sitting_date and sitting_date < CHIEF_MINISTER_CUTOFF
                else "Lim Yew Hock"
            )
            _cm_canonical, _cm_parl = _resolve(_cm_name, 0, lookups, speaker_id_lookup)
            _cm_sid = speaker_id_lookup.get((_cm_canonical, _cm_parl)) if _cm_canonical else None
            if _cm_sid:
                passed += 1
            else:
                failed.append((speech_id, speaker, parliament, _cm_canonical))
            continue

        # Role-only strings — resolve by parliament→person mapping.
        _role_key: tuple[str, int] | None = (raw, parliament) if parliament != 0 else None
        if _role_key is None:
            for _fb in COLONIAL_PARLIAMENT_FALLBACKS:
                if (raw, _fb) in ROLE_ONLY_SPEAKERS:
                    _role_key = (raw, _fb)
                    break
        if _role_key and _role_key in ROLE_ONLY_SPEAKERS:
            _role_name = ROLE_ONLY_SPEAKERS[_role_key]
            _role_canonical, _role_parl = _resolve(_role_name, _role_key[1], lookups, speaker_id_lookup)
            _role_sid = speaker_id_lookup.get((_role_canonical, _role_parl)) if _role_canonical else None
            if _role_sid:
                passed += 1
            else:
                failed.append((speech_id, speaker, parliament, _role_canonical))
            continue  # role-only strings are never resolvable via the name cascade

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
