"""
Find the most common Speaker and Deputy Speaker per parliament.

Scans the PRESENT section of every Sitting.markdown_content for lines that
contain "SPEAKER", resolves the name via the full SpeakerLookups cascade, and
tallies resolved names per parliament per role.  Prints a ready-to-paste Python
dict literal for _PRESIDING_OFFICERS in populate/speaker_links.py.

Usage:
    python -m scripts.find_presiding_officers
"""
from collections import Counter, defaultdict

from sqlmodel import Session

from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from database.init import engine
from services.attendance import (
    _extract_section_lines,
    _parse_speaker_line,
    build_speaker_lookups,
    infer_parliament,
    normalize_name,
    resolve_canonical_name,
)


def main() -> None:
    with Session(engine) as session:
        sittings = CRUDSitting(session).get_all()
        speakers = CRUDSpeaker(session).get_all()

    lookups = build_speaker_lookups(speakers)

    # role -> parliament -> Counter(canonical_name)
    tallies: dict[str, dict[int, Counter]] = {
        "SPEAKER": defaultdict(Counter),
        "DEPUTY SPEAKER": defaultdict(Counter),
    }

    for sitting in sittings:
        if not sitting.markdown_content:
            continue
        parliament = infer_parliament(sitting)
        if parliament is None:
            continue

        for line in _extract_section_lines(sitting.markdown_content, "PRESENT"):
            stripped = line.strip()
            if "SPEAKER" not in stripped:
                continue

            if "DEPUTY" in stripped:
                role = "DEPUTY SPEAKER"
            else:
                role = "SPEAKER"

            name, _location = _parse_speaker_line(stripped)
            if not name or name == "SPEAKER":
                continue

            name = normalize_name(name)
            canonical = resolve_canonical_name(name, parliament, lookups) or name
            tallies[role][parliament][canonical] += 1

    all_parliaments = sorted(
        set(tallies["SPEAKER"]) | set(tallies["DEPUTY SPEAKER"])
    )

    print("_PRESIDING_OFFICERS: dict[tuple[str, int], str] = {")
    for parliament in all_parliaments:
        for role in ("SPEAKER", "DEPUTY SPEAKER"):
            counter = tallies[role].get(parliament)
            if not counter:
                continue
            best_name, _count = counter.most_common(1)[0]
            print(f'    ("{role}", {parliament}): "{best_name}",')
    print("}")


if __name__ == "__main__":
    main()
