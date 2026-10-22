from collections import Counter, defaultdict

from sqlmodel import Session

from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from database.init import engine
from services.attendance import (
    AttendanceSection,
    build_speaker_lookups,
    extract_section_lines,
    parse_speaker_line,
)
from utils.names import (
    normalize_name,
)
from utils.parliament_numbers import infer_parliament
from utils.speaker_resolution import resolve_canonical_name

_SPEAKER_ROLE = "SPEAKER"
_DEPUTY_SPEAKER_ROLE = "DEPUTY SPEAKER"
_ROLES = (_SPEAKER_ROLE, _DEPUTY_SPEAKER_ROLE)


def main() -> None:
    with Session(engine) as session:
        sittings = CRUDSitting(session).get_all()
        speakers = CRUDSpeaker(session).get_all()

    lookups = build_speaker_lookups(speakers)
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

        for line in extract_section_lines(sitting.markdown_content, AttendanceSection.PRESENT):
            stripped = line.strip()
            if _SPEAKER_ROLE not in stripped:
                continue

            if "DEPUTY" in stripped:
                role = _DEPUTY_SPEAKER_ROLE
            else:
                role = _SPEAKER_ROLE

            parsed_speaker = parse_speaker_line(stripped)
            if not parsed_speaker.name or parsed_speaker.name == _SPEAKER_ROLE:
                continue

            name = normalize_name(parsed_speaker.name)
            canonical_name = resolve_canonical_name(name, parliament, lookups) or name
            role_to_parliament_to_name_counts[role][parliament][canonical_name] += 1

    all_parliaments = sorted(
        set(role_to_parliament_to_name_counts[_SPEAKER_ROLE]) | set(role_to_parliament_to_name_counts[_DEPUTY_SPEAKER_ROLE])
    )

    print("_PRESIDING_OFFICERS: dict[tuple[str, int], str] = {")  # noqa: T201 stdout is the dict literal to paste into the source
    for parliament in all_parliaments:
        for role in _ROLES:
            counter = role_to_parliament_to_name_counts[role].get(parliament)
            if not counter:
                continue
            best_name, _count = counter.most_common(1)[0]
            print(f'    ("{role}", {parliament}): "{best_name}",')  # noqa: T201 stdout is the dict literal to paste into the source
    print("}")  # noqa: T201 stdout is the dict literal to paste into the source


if __name__ == "__main__":
    main()
