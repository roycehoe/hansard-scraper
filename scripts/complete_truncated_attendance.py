import argparse
import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from database.attendance import Attendance
from database.init import engine
from database.sitting import Sitting
from exceptions import HansardWriteCheckError
from logs import logger
from services.attendance import (
    SpeakerLookups,
    build_constituency_lookups,
    build_speaker_lookups,
    get_sitting_attendance,
    resolve_canonical_name,
)
from utils.data_files import get_constituency_names
from utils.names import normalize_name, strip_title
from utils.parliament_numbers import infer_parliament
from utils.write_target import validate_can_write

_COLONIAL_PARLIAMENT_NUMBER = 0


@dataclass(frozen=True)
class TruncatedSitting:
    sitting_date: str
    markdown_md5: str
    stored_row_count: int
    parsed_row_count: int


_SITTING_ID_TO_TRUNCATED_SITTING = {
    5941: TruncatedSitting("2-12-1996", "ccd9bcfdd3caeb39f9f939d8f530f4f9", 53, 85),
    5988: TruncatedSitting("25-3-1986", "31bfb7caa21737c22d246f840c931ed0", 5, 79),
    6009: TruncatedSitting("20-7-2005", "31dc2d9dccd2d994a2e0834426e91369", 50, 94),
}


@dataclass(frozen=True)
class SittingCompletion:
    sitting_id: int
    rows_to_insert: list[Attendance]


def _get_speaker_id(
    speaker_name: str,
    parliament: int,
    lookups: SpeakerLookups,
    speaker_id_lookup: dict[tuple[str, int], int],
) -> Optional[int]:
    speaker_id = speaker_id_lookup.get((speaker_name, parliament))
    if speaker_id is not None:
        return speaker_id
    canonical = resolve_canonical_name(normalize_name(strip_title(speaker_name)), parliament, lookups)
    if canonical is None:
        return None
    return speaker_id_lookup.get((canonical, parliament))


def build_completions(session: Session, sitting_ids: list[int]) -> list[SittingCompletion]:
    speakers = CRUDSpeaker(session).get_all()
    lookups = build_speaker_lookups(speakers)
    constituency_lookups = build_constituency_lookups(get_constituency_names())
    speaker_id_lookup = {
        (speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None
    }
    date_rows = {date_row.id: date_row for date_row in CRUDSitting(session).get_date_rows()}
    sitting_id_to_row_count = {count.sitting_id: count.row_count for count in CRUDAttendance(session).get_sitting_counts()}
    sitting_id_to_presence_keys: dict[int, Counter] = {sitting_id: Counter() for sitting_id in sitting_ids}
    for presence_row in CRUDAttendance(session).get_presence_rows_by_speaker_id_not_null():
        if presence_row.sitting_id in sitting_id_to_presence_keys:
            sitting_id_to_presence_keys[presence_row.sitting_id][(presence_row.speaker_id, presence_row.is_present)] += 1
    date_to_markdown = CRUDSitting(session).get_markdown_by_dates(
        [_SITTING_ID_TO_TRUNCATED_SITTING[sitting_id].sitting_date for sitting_id in sitting_ids]
    )

    completions = []
    for sitting_id in sitting_ids:
        expected = _SITTING_ID_TO_TRUNCATED_SITTING[sitting_id]
        date_row = date_rows[sitting_id]
        if date_row.sitting_date != expected.sitting_date:
            raise HansardWriteCheckError(f"sitting {sitting_id}: date is {date_row.sitting_date}, expected {expected.sitting_date}")
        markdown = date_to_markdown[expected.sitting_date]
        if hashlib.md5(markdown.encode("utf-8")).hexdigest() != expected.markdown_md5:
            raise HansardWriteCheckError(f"sitting {sitting_id}: markdown changed since the dry run")
        if sitting_id_to_row_count.get(sitting_id, 0) != expected.stored_row_count:
            raise HansardWriteCheckError(f"sitting {sitting_id}: {sitting_id_to_row_count.get(sitting_id, 0)} stored rows, expected {expected.stored_row_count}")

        parliament = infer_parliament(date_row.parlement_no, date_row.volume_no)
        if parliament is None or parliament == _COLONIAL_PARLIAMENT_NUMBER:
            raise HansardWriteCheckError(f"sitting {sitting_id}: parliament {parliament} needs the colonial fallback")
        sitting = Sitting(
            id=sitting_id,
            sitting_date=date_row.sitting_date,
            markdown_content=markdown,
            parlement_no=date_row.parlement_no,
            volume_no=date_row.volume_no,
        )
        parsed_rows = get_sitting_attendance(sitting, lookups, constituency_lookups)
        if len(parsed_rows) != expected.parsed_row_count:
            raise HansardWriteCheckError(f"sitting {sitting_id}: parse gives {len(parsed_rows)} rows, expected {expected.parsed_row_count}")
        for parsed_row in parsed_rows:
            parsed_row.speaker_id = _get_speaker_id(parsed_row.speaker_name, parliament, lookups, speaker_id_lookup)

        stored_prefix = parsed_rows[: expected.stored_row_count]
        prefix_keys = Counter((row.speaker_id, row.is_present) for row in stored_prefix if row.speaker_id is not None)
        if prefix_keys != sitting_id_to_presence_keys[sitting_id]:
            raise HansardWriteCheckError(f"sitting {sitting_id}: stored rows are not the first {expected.stored_row_count} parsed rows")
        completions.append(SittingCompletion(sitting_id, parsed_rows[expected.stored_row_count :]))
    return completions


def _write_attendance(session: Session, rows_to_insert: list[Attendance], sitting_ids: list[int]) -> None:
    CRUDAttendance(session).add_many(rows_to_insert)
    sitting_id_to_row_count = {count.sitting_id: count.row_count for count in CRUDAttendance(session).get_sitting_counts()}
    for sitting_id in sitting_ids:
        expected = _SITTING_ID_TO_TRUNCATED_SITTING[sitting_id]
        row_count = sitting_id_to_row_count.get(sitting_id, 0)
        if row_count != expected.parsed_row_count:
            session.rollback()
            raise HansardWriteCheckError(f"sitting {sitting_id}: {row_count} rows after the write, expected {expected.parsed_row_count}")
    session.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sitting_ids", type=int, nargs="+", choices=sorted(_SITTING_ID_TO_TRUNCATED_SITTING))
    parser.add_argument("--commit", action="store_true")
    arguments = parser.parse_args()
    is_commit = arguments.commit
    sitting_ids = sorted(set(arguments.sitting_ids))

    if is_commit:
        validate_can_write(str(engine.url))
    with Session(engine) as session:
        completions = build_completions(session, sitting_ids)
        rows_to_insert = [row for completion in completions for row in completion.rows_to_insert]
        for completion in completions:
            linked = sum(row.speaker_id is not None for row in completion.rows_to_insert)
            logger.info(f"Sitting {completion.sitting_id}: insert {len(completion.rows_to_insert)} rows, {linked} linked")
        logger.info(f"Attendance: insert {len(rows_to_insert)} rows, delete 0, update 0")
        sitting_id_to_stored_row_count = {
            count.sitting_id: count.row_count for count in CRUDAttendance(session).get_sitting_counts()
        }
        for completion in completions:
            expected = _SITTING_ID_TO_TRUNCATED_SITTING[completion.sitting_id]
            stored_row_count = sitting_id_to_stored_row_count.get(completion.sitting_id, 0)
            if stored_row_count + len(completion.rows_to_insert) != expected.parsed_row_count:
                raise HansardWriteCheckError(
                    f"sitting {completion.sitting_id}: {stored_row_count} stored + {len(completion.rows_to_insert)} to insert"
                    f" != {expected.parsed_row_count} parsed"
                )
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        _write_attendance(session, rows_to_insert, sitting_ids)
        logger.info("Attendance: row counts verified and write committed")


if __name__ == "__main__":
    main()
