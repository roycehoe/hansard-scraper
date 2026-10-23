from collections import defaultdict
from datetime import date

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
from utils.sitting_dates import parse_sitting_date
from utils.speaker_resolution import resolve_canonical_name

_SPEAKER_ROLE = "SPEAKER"
_DEPUTY_SPEAKER_ROLE = "DEPUTY SPEAKER"
_SPEAKER_TERMS_NAME = "SPEAKER_TERMS"
_DEPUTY_SPEAKER_TERMS_NAME = "DEPUTY_SPEAKER_TERMS"


def _print_terms(terms_name: str, parliament_number_to_name_to_dates: dict[int, dict[str, list[date]]]) -> None:
    print(f"{terms_name}: tuple[tuple[date, date, str], ...] = (")  # noqa: T201 stdout is the tuple literal to paste into the source
    for parliament_number in sorted(parliament_number_to_name_to_dates):
        name_to_dates = parliament_number_to_name_to_dates[parliament_number]
        best_name = max(name_to_dates, key=lambda name: len(name_to_dates[name]))
        first_day, last_day = min(name_to_dates[best_name]), max(name_to_dates[best_name])
        print(f'    (date({first_day.year}, {first_day.month}, {first_day.day}), date({last_day.year}, {last_day.month}, {last_day.day}), "{best_name}"),')  # noqa: T201 stdout is the tuple literal to paste into the source
    print(")")  # noqa: T201 stdout is the tuple literal to paste into the source


def find_presiding_officers() -> None:
    with Session(engine) as session:
        sittings = CRUDSitting(session).get_all()
        speakers = CRUDSpeaker(session).get_all()

    lookups = build_speaker_lookups(speakers)
    role_to_parliament_number_to_name_to_dates: dict[str, dict[int, dict[str, list[date]]]] = {
        _SPEAKER_ROLE: defaultdict(lambda: defaultdict(list)),
        _DEPUTY_SPEAKER_ROLE: defaultdict(lambda: defaultdict(list)),
    }

    for sitting in sittings:
        if not sitting.markdown_content:
            continue
        parliament_number = infer_parliament(sitting.parlement_no, sitting.volume_no)
        if parliament_number is None:
            continue
        sitting_day = parse_sitting_date(sitting.sitting_date).date()

        for line in extract_section_lines(sitting.markdown_content, AttendanceSection.PRESENT):
            stripped = line.strip()
            if _SPEAKER_ROLE not in stripped:
                continue

            role = _DEPUTY_SPEAKER_ROLE if "DEPUTY" in stripped else _SPEAKER_ROLE

            parsed_speaker = parse_speaker_line(stripped)
            if not parsed_speaker.name or parsed_speaker.name == _SPEAKER_ROLE:
                continue

            name = normalize_name(parsed_speaker.name)
            canonical_name = resolve_canonical_name(name, parliament_number, lookups) or name
            role_to_parliament_number_to_name_to_dates[role][parliament_number][canonical_name].append(sitting_day)

    _print_terms(_SPEAKER_TERMS_NAME, role_to_parliament_number_to_name_to_dates[_SPEAKER_ROLE])
    _print_terms(_DEPUTY_SPEAKER_TERMS_NAME, role_to_parliament_number_to_name_to_dates[_DEPUTY_SPEAKER_ROLE])


if __name__ == "__main__":
    find_presiding_officers()
