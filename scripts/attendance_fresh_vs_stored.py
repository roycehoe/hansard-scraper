import argparse
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.attendance import AttendanceSpeakerRow, CRUDAttendance
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from database.attendance import Attendance
from database.init import engine
from database.sitting import Sitting
from logs import logger
from schemas.hansard_report_response import HansardReportAttendanceEntry
from services.attendance import (
    AttendanceSection,
    ConstituencyLookups,
    build_constituency_lookups,
    build_sitting_attendances,
    build_speaker_lookups,
    extract_section_lines,
    parse_entry_line,
    split_entry_line,
)
from services.speaker_link import resolve_attendance_rows
from utils.data_files import get_constituency_names
from utils.names import normalize_name
from utils.parliament_numbers import infer_parliament
from utils.speaker_resolution import SpeakerLookups, resolve_canonical_name

_MAX_BATCH_ROWS = 150
_ACTING_LOCATION = "Acting"
_OCR_NAME_RE = re.compile(r"\blbrahim\b")
_LEAVE_NOTE_PREFIX = "For information on permission given to Members for leave of absence"
_STORED_ONLY = "stored_only"
_FRESH_ONLY = "fresh_only"
_ACTING_LOCATION_CLASS = "acting_location"
_OCR_LBRAHIM_CLASS = "ocr_lbrahim"
_STORED_WITHOUT_SPEAKER_ID_CLASS = "stored_without_speaker_id"
_FIELDS = ("speaker_name", "is_present", "location_name", "speaker_id")


@dataclass(frozen=True)
class RowView:
    id: Optional[int]
    speaker_name: Optional[str]
    is_present: Optional[bool]
    location_name: Optional[str]
    speaker_id: Optional[int]

    def get_key(self) -> tuple[Optional[str], Optional[bool], Optional[str], Optional[int]]:
        return (self.speaker_name, self.is_present, self.location_name, self.speaker_id)


@dataclass(frozen=True)
class RowDifference:
    stored: Optional[RowView]
    fresh: Optional[RowView]
    differing_fields: tuple[str, ...]
    difference_class: str


@dataclass(frozen=True)
class RowPair:
    stored: RowView
    fresh: RowView


@dataclass(frozen=True)
class RowPairing:
    pairs: list[RowPair]
    remaining_stored: list[RowView]
    remaining_fresh: list[RowView]


@dataclass(frozen=True)
class SourceEntry:
    section: str
    line: str


def _get_differing_fields(stored: RowView, fresh: RowView) -> tuple[str, ...]:
    return tuple(field for field in _FIELDS if getattr(stored, field) != getattr(fresh, field))


def _get_difference_class(stored: Optional[RowView], fresh: Optional[RowView], differing_fields: tuple[str, ...]) -> str:
    if stored is not None and stored.location_name == _ACTING_LOCATION:
        return _ACTING_LOCATION_CLASS
    if any(row is not None and row.speaker_name is not None and _OCR_NAME_RE.search(row.speaker_name) for row in (stored, fresh)):
        return _OCR_LBRAHIM_CLASS
    if stored is not None and stored.speaker_id is None:
        return _STORED_WITHOUT_SPEAKER_ID_CLASS
    if stored is None:
        return _FRESH_ONLY
    if fresh is None:
        return _STORED_ONLY
    return "differs_" + "_".join(differing_fields)


def _pair_rows(
    unmatched_stored: list[RowView], unmatched_fresh: list[RowView], is_paired: Callable[[RowView, RowView], bool]
) -> RowPairing:
    pairs = []
    remaining_stored = []
    remaining_fresh = list(unmatched_fresh)
    for stored in unmatched_stored:
        match_index = next((index for index, fresh in enumerate(remaining_fresh) if is_paired(stored, fresh)), None)
        if match_index is None:
            remaining_stored.append(stored)
        else:
            pairs.append(RowPair(stored, remaining_fresh.pop(match_index)))
    return RowPairing(pairs, remaining_stored, remaining_fresh)


def _get_watched_class(row: RowView) -> Optional[str]:
    if row.location_name == _ACTING_LOCATION:
        return _ACTING_LOCATION_CLASS
    if row.speaker_name is not None and _OCR_NAME_RE.search(row.speaker_name):
        return _OCR_LBRAHIM_CLASS
    if row.speaker_id is None:
        return _STORED_WITHOUT_SPEAKER_ID_CLASS
    return None


def get_row_differences(stored_rows: list[RowView], fresh_rows: list[RowView]) -> list[RowDifference]:
    fresh_key_to_count = Counter(fresh.get_key() for fresh in fresh_rows)
    unmatched_stored = []
    watched_equal_rows = []
    for stored in stored_rows:
        if fresh_key_to_count[stored.get_key()] > 0:
            fresh_key_to_count[stored.get_key()] -= 1
            watched_class = _get_watched_class(stored)
            if watched_class is not None:
                watched_equal_rows.append(RowDifference(stored, RowView(None, *stored.get_key()), (), watched_class))
        else:
            unmatched_stored.append(stored)
    unmatched_fresh = []
    for fresh in fresh_rows:
        if fresh_key_to_count[fresh.get_key()] > 0:
            fresh_key_to_count[fresh.get_key()] -= 1
            unmatched_fresh.append(fresh)

    name_pairing = _pair_rows(unmatched_stored, unmatched_fresh, lambda stored, fresh: stored.speaker_name == fresh.speaker_name)
    id_pairing = _pair_rows(
        name_pairing.remaining_stored,
        name_pairing.remaining_fresh,
        lambda stored, fresh: stored.speaker_id is not None and stored.speaker_id == fresh.speaker_id,
    )
    differences = watched_equal_rows
    for pair in [*name_pairing.pairs, *id_pairing.pairs]:
        differing_fields = _get_differing_fields(pair.stored, pair.fresh)
        differences.append(RowDifference(pair.stored, pair.fresh, differing_fields, _get_difference_class(pair.stored, pair.fresh, differing_fields)))
    differences.extend(RowDifference(stored, None, (), _get_difference_class(stored, None, ())) for stored in id_pairing.remaining_stored)
    differences.extend(RowDifference(None, fresh, (), _get_difference_class(None, fresh, ())) for fresh in id_pairing.remaining_fresh)
    return differences


def _iter_source_entries(sitting: Sitting) -> Iterator[SourceEntry]:
    if sitting.markdown_content is not None:
        for section in AttendanceSection:
            for line in extract_section_lines(sitting.markdown_content, section):
                for entry_line in split_entry_line(line):
                    yield SourceEntry(section.value, entry_line.strip())
    elif sitting.attendance_list is not None:
        for raw_entry in json.loads(sitting.attendance_list):
            entry = HansardReportAttendanceEntry.model_validate(raw_entry)
            if entry.mp_name is not None and not entry.mp_name.startswith(_LEAVE_NOTE_PREFIX):
                yield SourceEntry("PRESENT" if entry.attendance else "ABSENT", entry.mp_name.strip())


def _get_source_lines(sitting: Sitting, row: Optional[RowView], other: Optional[RowView], lookups: SpeakerLookups) -> list[str]:
    names = {name for name in (row.speaker_name if row else None, other.speaker_name if other else None) if name}
    parliament_number = infer_parliament(sitting.parlement_no, sitting.volume_no)
    exact_lines = []
    token_lines = []
    tokens = {name.split()[-1].lower() for name in names if name.split()}
    for entry in _iter_source_entries(sitting):
        parsed = parse_entry_line(entry.line, sitting.sitting_date)
        if parsed is not None and parsed.name:
            name = normalize_name(parsed.name)
            canonical_name = None if parliament_number is None else resolve_canonical_name(name, parliament_number, lookups)
            if (canonical_name or name) in names:
                exact_lines.append(f"{entry.section}: {entry.line}")
                continue
        if any(token in entry.line.lower() for token in tokens):
            token_lines.append(f"{entry.section}: {entry.line}")
    return exact_lines or token_lines


def _get_row_view(attendance: Attendance) -> RowView:
    return RowView(attendance.id, attendance.speaker_name, attendance.is_present, attendance.location_name, attendance.speaker_id)


def _get_fresh_views(
    sitting: Sitting, lookups: SpeakerLookups, constituency_lookups: ConstituencyLookups, name_parliament_number_to_speaker_id: dict[tuple[str, int], int]
) -> list[RowView]:
    built_rows = build_sitting_attendances(sitting, lookups, constituency_lookups)
    resolved_speaker_ids = resolve_attendance_rows(
        [AttendanceSpeakerRow(index, built.speaker_name, sitting.parlement_no, sitting.volume_no) for index, built in enumerate(built_rows)],
        lookups,
        name_parliament_number_to_speaker_id,
    )
    return [
        RowView(None, built.speaker_name, built.is_present, built.location_name, resolved_speaker_ids.id_to_speaker_id.get(index))
        for index, built in enumerate(built_rows)
    ]


def _write_batches(class_to_records: dict[str, list[dict]], batches_directory: Path) -> int:
    batches_directory.mkdir(parents=True, exist_ok=True)
    batch_count = 0
    for difference_class, records in sorted(class_to_records.items()):
        for start in range(0, len(records), _MAX_BATCH_ROWS):
            batch_count += 1
            batch_path = batches_directory / f"{difference_class}-{start // _MAX_BATCH_ROWS + 1:02d}.json"
            batch_path.write_text(json.dumps(
                {"class": difference_class, "rows": records[start : start + _MAX_BATCH_ROWS]}, indent=1, ensure_ascii=False
            ))
    return batch_count


def attendance_fresh_vs_stored(output_path: Path, batches_directory: Optional[Path]) -> None:
    with Session(engine) as session:
        speakers = CRUDSpeaker(session).get_all()
        lookups = build_speaker_lookups(speakers)
        constituency_lookups = build_constituency_lookups(get_constituency_names())
        name_parliament_number_to_speaker_id = {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None}
        sitting_id_to_stored: dict[int, list[RowView]] = defaultdict(list)
        for attendance in CRUDAttendance(session).get_all():
            sitting_id_to_stored[attendance.sitting_id].append(_get_row_view(attendance))
        sittings = sorted(CRUDSitting(session).get_all(), key=lambda sitting: sitting.id)
        class_to_records: dict[str, list[dict]] = defaultdict(list)
        fresh_row_count = 0
        with output_path.open("w") as output_file:
            for sitting in sittings:
                sitting_id = sitting.id
                fresh_rows = _get_fresh_views(sitting, lookups, constituency_lookups, name_parliament_number_to_speaker_id)
                fresh_row_count += len(fresh_rows)
                for difference in get_row_differences(sitting_id_to_stored[sitting_id], fresh_rows):
                    record = {
                        "class": difference.difference_class,
                        "sitting_id": sitting_id,
                        "sitting_date": sitting.sitting_date,
                        "build_path": "markdown" if sitting.markdown_content is not None else "attendance_list",
                        "differing_fields": list(difference.differing_fields),
                        "stored": asdict(difference.stored) if difference.stored else None,
                        "fresh": asdict(difference.fresh) if difference.fresh else None,
                        "source_lines": _get_source_lines(sitting, difference.stored, difference.fresh, lookups),
                    }
                    output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    class_to_records[difference.difference_class].append(record)
    logger.info(f"{sum(len(rows) for rows in sitting_id_to_stored.values())} stored rows, {fresh_row_count} fresh rows, {sum(1 for rows in sitting_id_to_stored.values() for row in rows if row.location_name == _ACTING_LOCATION)} stored Acting, {sum(1 for rows in sitting_id_to_stored.values() for row in rows if row.speaker_id is None)} stored without speaker_id")
    logger.info(f"{len(sittings)} sittings, {sum(len(records) for records in class_to_records.values())} differing rows")
    for difference_class, records in sorted(class_to_records.items()):
        logger.info(f"{len(records)} rows: {difference_class}")
    if batches_directory is not None:
        logger.info(f"{_write_batches(class_to_records, batches_directory)} batch files in {batches_directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare the attendance rows stage 7 builds now with the stored rows, read only")
    parser.add_argument("--output", type=Path, required=True, help="write one JSON line per differing row to this path")
    parser.add_argument("--batches", type=Path, help="write reader batches of at most 150 rows per class to this directory")
    arguments = parser.parse_args()
    attendance_fresh_vs_stored(arguments.output, arguments.batches)
