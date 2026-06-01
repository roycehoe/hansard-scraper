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

from database.init import engine
from database.sitting import Sitting
from services.attendance import (
    get_sitting_attendance,
    infer_parliament,
    resolve_canonical_name,
)

# ── categorisation ────────────────────────────────────────────────────────────

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


def _categorise(name: str) -> str:
    s = name.strip()
    if not s:
        return "blank"
    if _PRESIDING_RE.search(s):
        return "presiding"
    if _OFFICIAL_TITLE_RE.search(s):
        return "official_with_title"
    alpha = re.sub(r"[^A-Za-z]", "", s)
    if alpha and alpha == alpha.upper() and len(alpha) >= 4:
        return "allcaps_header"
    if _DOCUMENT_NOISE_RE.search(s):
        return "document_noise"
    return "candidate"


# ── resolution ────────────────────────────────────────────────────────────────

def _resolved(name: str, parliament: int) -> bool:
    if resolve_canonical_name(name, parliament):
        return True
    if parliament == 0:
        for fb in [1, 2, 3]:
            if resolve_canonical_name(name, fb):
                return True
    return False


# ── main ──────────────────────────────────────────────────────────────────────

def find_unmatched(*, verbose: bool = False) -> dict[str, Counter]:
    """
    Returns a dict mapping category -> Counter(speaker_name -> count).
    Categories: 'candidate', 'official_with_title', 'presiding',
                'allcaps_header', 'document_noise', 'blank'.
    """
    with Session(engine) as session:
        sittings = session.exec(select(Sitting)).all()

    buckets: dict[str, Counter] = {
        "candidate": Counter(),
        "official_with_title": Counter(),
        "presiding": Counter(),
        "allcaps_header": Counter(),
        "document_noise": Counter(),
        "blank": Counter(),
    }
    total = len(sittings)

    for i, sitting in enumerate(sittings, 1):
        if verbose and i % 100 == 0:
            print(f"  {i}/{total} sittings processed…", file=sys.stderr)
        parliament = infer_parliament(sitting)
        if parliament is None:
            continue
        for rec in get_sitting_attendance(sitting):
            if not rec.speaker_name:
                continue
            if _resolved(rec.speaker_name, parliament):
                continue
            cat = _categorise(rec.speaker_name)
            buckets[cat][rec.speaker_name] += 1

    return buckets


def _json_template(name: str) -> dict:
    return {
        "name": name,
        "party": "Unknown",
        "parliament_number": 1,
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
    args = parser.parse_args()

    print("Scanning sittings…", file=sys.stderr)
    buckets = find_unmatched(verbose=args.verbose)

    # ── print report ─────────────────────────────────────────────────────────
    candidates = buckets["candidate"]
    total_unmatched = sum(sum(c.values()) for c in buckets.values())
    total_candidates = sum(candidates.values())

    print(f"\nUnmatched attendance rows: {total_unmatched}")
    print(f"  Candidates (likely real people, no Speaker entry): {total_candidates}")
    for cat, ctr in buckets.items():
        if cat == "candidate":
            continue
        if ctr:
            print(f"  {cat}: {sum(ctr.values())}")

    if candidates:
        print(f"\nTop candidates ({len(candidates)} distinct names):\n")
        print(f"  {'Count':>6}  Name")
        print(f"  {'─'*6}  {'─'*50}")
        for name, count in candidates.most_common():
            print(f"  {count:>6}  {name}")

    # ── write JSON template ───────────────────────────────────────────────────
    if args.json:
        template = [_json_template(name) for name, _ in candidates.most_common()]
        path = args.json
        with open(path, "w") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
        print(f"\nWrote {len(template)}-entry template to {path}", file=sys.stderr)
        print("Edit party/parliament_number/comments, then append to data/colonial_la_members.json", file=sys.stderr)


if __name__ == "__main__":
    main()
