"""
Find the most common Speaker and Deputy Speaker per parliament.

Scans the PRESENT section of every Sitting.markdown_content for lines that
contain "SPEAKER", resolves the name via the full SpeakerLookups cascade, and
role_to_parliament_to_name_counts resolved names per parliament per role.  Prints a ready-to-paste Python
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
    resolve_canonical_name,
)
from utils.names import (
    normalize_name,
)

_SPEAKER_ROLE = "SPEAKER"
_DEPUTY_SPEAKER_ROLE = "DEPUTY SPEAKER"
_ROLES = (_SPEAKER_ROLE, _DEPUTY_SPEAKER_ROLE)
_PRESENT_SECTION = "PRESENT"


def main() -> None:
    with Session(engine) as session:
        sittings = CRUDSitting(session).get_all()
        speakers = CRUDSpeaker(session).get_all()

    lookups = build_speaker_lookups(speakers)

    # role -> parliament -> Counter(canonical_name)
    role_to_parliament_to_name_counts: dict[str, dict[int, Counter]] = {
        _SPEAKER_ROLE: defaultdict(Counter),
        _DEPUTY_SPEAKER_ROLE: defaultdict(Counter),
    }

    for sitting in sittings:
        if not sitting.markdown_content:
            continue
        parliament = infer_parliament(sitting.parlement_no, sitting.volume_no)
        if parliament is None:
            continue

        for line in _extract_section_lines(sitting.markdown_content, _PRESENT_SECTION):
            stripped = line.strip()
            if _SPEAKER_ROLE not in stripped:
                continue

            if "DEPUTY" in stripped:
                role = _DEPUTY_SPEAKER_ROLE
            else:
                role = _SPEAKER_ROLE

            parsed_speaker = _parse_speaker_line(stripped)
            if not parsed_speaker.name or parsed_speaker.name == _SPEAKER_ROLE:
                continue

            name = normalize_name(parsed_speaker.name)
            canonical_name = resolve_canonical_name(name, parliament, lookups) or name
            role_to_parliament_to_name_counts[role][parliament][canonical_name] += 1

    all_parliaments = sorted(
        set(role_to_parliament_to_name_counts[_SPEAKER_ROLE]) | set(role_to_parliament_to_name_counts[_DEPUTY_SPEAKER_ROLE])
    )

    print("_PRESIDING_OFFICERS: dict[tuple[str, int], str] = {")
    for parliament in all_parliaments:
        for role in _ROLES:
            counter = role_to_parliament_to_name_counts[role].get(parliament)
            if not counter:
                continue
            best_name, _count = counter.most_common(1)[0]
            print(f'    ("{role}", {parliament}): "{best_name}",')
    print("}")


if __name__ == "__main__":
    main()
