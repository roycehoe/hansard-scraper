"""
Find attendance names with no match in the current Speaker table.

Iterates all Sitting records, parses attendance via get_sitting_attendance,
and groups unresolved names by frequency.  Run this after adding new Speaker rows
to discover remaining gaps for colonial_la_members.json.

Usage:
    python -m scripts.find_unmatched_attendees
    python -m scripts.find_unmatched_attendees --json candidates.json
"""
import argparse
import json
import re
import sys
from collections import Counter

from sqlmodel import Session, select

from crud.speaker import CRUDSpeaker
from database.init import engine
from database.sitting import Sitting
from services.attendance import (
    build_speaker_lookups,
    get_sitting_attendance,
    infer_parliament,
    resolve_canonical_name,
)

# ── categorisation ────────────────────────────────────────────────────────────

_MIN_ALLCAPS_HEADER_LETTERS = 4
_PROGRESS_INTERVAL = 100
_COLONIAL_PARLIAMENT_NUMBER = 0
_COLONIAL_PARLIAMENT_FALLBACKS = (1, 2, 3)
_COUNT_COLUMN_WIDTH = 6
_NAME_COLUMN_WIDTH = 50
_TEMPLATE_PARTY = "Unknown"
_TEMPLATE_PARLIAMENT_NUMBER = 1

_OFFICIAL_TITLE_RE = re.compile(
    r",\s*(?:Financial|Chief|Colonial|Acting\s+Chief)\s+Secretary"
    r"|,\s*Attorney[-\s]General"
    r"|\b(?:Q\.C\.|C\.M\.G\.|O\.B\.E\.)\b",
    re.I,
)
_PRESIDING_RE = re.compile(r"\bSpeaker\b|\bChairman\b", re.I)
_DOCUMENT_NOISE_RE = re.compile(
    r"^\|"
    r"|^\*\*Column"
    r"|^[0-9]"
    r"|\b(the|have|been|informed|that|following|shall|order|read|resumption|debate|motion|question|bill|report|budget|committee|national|total|year|country)\b",
    re.I,
)


def _get_category(name: str) -> str:
    stripped_name = name.strip()
    if not stripped_name:
        return "blank"
    if _PRESIDING_RE.search(stripped_name):
        return "presiding"
    if _OFFICIAL_TITLE_RE.search(stripped_name):
        return "official_with_title"
    alpha = re.sub(r"[^A-Za-z]", "", stripped_name)
    if alpha and alpha == alpha.upper() and len(alpha) >= _MIN_ALLCAPS_HEADER_LETTERS:
        return "allcaps_header"
    if _DOCUMENT_NOISE_RE.search(stripped_name):
        return "document_noise"
    return "candidate"


# ── resolution ────────────────────────────────────────────────────────────────

def _is_resolved(name: str, parliament: int, lookups) -> bool:
    if resolve_canonical_name(name, parliament, lookups) is not None:
        return True
    if parliament == _COLONIAL_PARLIAMENT_NUMBER:
        for fallback_parliament in _COLONIAL_PARLIAMENT_FALLBACKS:
            if resolve_canonical_name(name, fallback_parliament, lookups) is not None:
                return True
    return False


# ── main ──────────────────────────────────────────────────────────────────────

def find_unmatched(is_verbose: bool = False) -> dict[str, Counter]:
    """
    Returns a dict mapping category -> Counter(speaker_name -> count).
    Categories: 'candidate', 'official_with_title', 'presiding',
                'allcaps_header', 'document_noise', 'blank'.
    """
    with Session(engine) as session:
        sittings = session.exec(select(Sitting)).all()
        speakers = CRUDSpeaker(session).get_all()

    lookups = build_speaker_lookups(speakers)

    category_to_counter: dict[str, Counter] = {
        "candidate": Counter(),
        "official_with_title": Counter(),
        "presiding": Counter(),
        "allcaps_header": Counter(),
        "document_noise": Counter(),
        "blank": Counter(),
    }
    total = len(sittings)

    for sitting_number, sitting in enumerate(sittings, 1):
        if is_verbose and sitting_number % _PROGRESS_INTERVAL == 0:
            print(f"  {sitting_number}/{total} sittings processed…", file=sys.stderr)
        parliament = infer_parliament(sitting.parlement_no, sitting.volume_no)
        if parliament is None:
            continue
        for attendance_record in get_sitting_attendance(sitting, lookups):
            if not attendance_record.speaker_name:
                continue
            if _is_resolved(attendance_record.speaker_name, parliament, lookups):
                continue
            category = _get_category(attendance_record.speaker_name)
            category_to_counter[category][attendance_record.speaker_name] += 1

    return category_to_counter


def _get_json_template(name: str) -> dict:
    return {
        "name": name,
        "party": _TEMPLATE_PARTY,
        "parliament_number": _TEMPLATE_PARLIAMENT_NUMBER,
        "is_legislative_assembly": True,
        "comments": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", metavar="FILE",
        help="Write candidate JSON template to FILE (ready to merge into colonial_la_members.json)",
    )
    parser.add_argument("--verbose", action="store_true")
    arguments = parser.parse_args()

    print("Scanning sittings…", file=sys.stderr)
    category_to_counter = find_unmatched(is_verbose=arguments.verbose)

    # ── print report ─────────────────────────────────────────────────────────
    candidates = category_to_counter["candidate"]
    total_unmatched = sum(sum(counter.values()) for counter in category_to_counter.values())
    total_candidates = sum(candidates.values())

    print(f"\nUnmatched attendance rows: {total_unmatched}")
    print(f"  Candidates (likely real people, no Speaker entry): {total_candidates}")
    for category, counter in category_to_counter.items():
        if category == "candidate":
            continue
        if counter:
            print(f"  {category}: {sum(counter.values())}")

    if candidates:
        print(f"\nTop candidates ({len(candidates)} distinct names):\n")
        print(f"  {'Count':>6}  Name")
        print(f"  {'─' * _COUNT_COLUMN_WIDTH}  {'─' * _NAME_COLUMN_WIDTH}")
        for name, count in candidates.most_common():
            print(f"  {count:>6}  {name}")

    # ── write JSON template ───────────────────────────────────────────────────
    if arguments.json:
        template = [_get_json_template(name) for name, _ in candidates.most_common()]
        path = arguments.json
        with open(path, "w") as file:
            json.dump(template, file, indent=2, ensure_ascii=False)
        print(f"\nWrote {len(template)}-entry template to {path}", file=sys.stderr)
        print("Edit party/parliament_number/comments, then append to data/colonial_la_members.json", file=sys.stderr)


if __name__ == "__main__":
    main()
