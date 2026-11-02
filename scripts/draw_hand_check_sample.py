import argparse
import hashlib
import math
import random
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.person import CRUDPerson
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech, SpeechFrameRow, SpeechParseRow, SpeechSnapshotRow
from database.init import build_read_only_engine
from database.speaker import Speaker
from exceptions import HansardHandCheckError
from logs import logger
from schemas.hand_check_snapshot import (
    HandCheckFrameSummary,
    HandCheckSnapshot,
    HandCheckSnapshotRow,
)
from services.attribution import get_group
from settings import settings
from utils.database_label import get_database_label

_MAIN_SEED = 20_261_111
_PILOT_SEED = 20_261_101
_MAIN_SAMPLE_SIZE = 1_000
_PILOT_SAMPLE_SIZE = 20
_MAX_WEIGHT_SPREAD = Fraction(3, 100)
_DRAW_ISOLATION_LEVEL = "REPEATABLE READ"
_SNAPSHOT_FILE_NAME = "snapshot.json"
_DRAW_TSV_FILE_NAME = "draw.tsv"
_SUMMARY_FILE_NAME = "draw-summary.txt"
_DRAW_TSV_HEADER = "speech_id\tgroup\tframe_position"


@dataclass(frozen=True)
class DrawnRow:
    speech_id: int
    group: str
    frame_position: int


@dataclass(frozen=True)
class Frame:
    group_to_speech_ids: dict[str, list[int]]
    frame_hash: str


def read_frame(frame_rows: Iterable[SpeechFrameRow]) -> Frame:
    group_to_speech_ids: dict[str, list[int]] = {}
    frame_hasher = hashlib.sha256()
    # NOTE: the database sorts the frame, so a speech id's index in its group's list is its place in the group
    for frame_row in frame_rows:
        group_to_speech_ids.setdefault(
            get_group(frame_row.parliament_number), []
        ).append(frame_row.id)
        frame_hasher.update(f"{frame_row.id}\n".encode("ascii"))
    return Frame(
        group_to_speech_ids=group_to_speech_ids, frame_hash=frame_hasher.hexdigest()
    )


def get_allocation(
    group_to_frame_count: dict[str, int], sample_size: int
) -> dict[str, int]:
    frame_count = sum(group_to_frame_count.values())
    group_to_quota = {
        group: Fraction(sample_size * group_frame_count, frame_count)
        for group, group_frame_count in group_to_frame_count.items()
    }
    group_to_allocation = {
        group: math.floor(quota) for group, quota in group_to_quota.items()
    }
    remainder_count = sample_size - sum(group_to_allocation.values())
    # NOTE: sorted keeps equal remainders in the order the groups are listed, so the first group wins a tie
    groups_to_round_up = sorted(
        group_to_quota,
        key=lambda group: group_to_quota[group] - group_to_allocation[group],
        reverse=True,
    )[:remainder_count]
    for group in groups_to_round_up:
        group_to_allocation[group] += 1
    return group_to_allocation


def get_weight_spread(
    group_to_frame_count: dict[str, int], group_to_allocation: dict[str, int]
) -> Fraction:
    weights = [
        Fraction(group_frame_count, group_to_allocation[group])
        for group, group_frame_count in group_to_frame_count.items()
    ]
    return max(weights) / min(weights) - 1


def validate_can_write_draw(
    group_to_allocation: dict[str, int],
    sample_size: int,
    weight_spread: Fraction,
    is_pilot: bool,
) -> None:
    allocated = sum(group_to_allocation.values())
    if allocated != sample_size:
        raise HansardHandCheckError(
            f"Refusing to write: the allocation sums to {allocated}, not {sample_size}"
        )
    if is_pilot:
        return
    if weight_spread > _MAX_WEIGHT_SPREAD:
        raise HansardHandCheckError(
            f"Refusing to write: the weights spread by {weight_spread}, over the limit of {_MAX_WEIGHT_SPREAD}"
        )


def get_group_to_start(
    group_to_frame_count: dict[str, int],
    group_to_allocation: dict[str, int],
    seed: int,
) -> dict[str, Fraction]:
    generator = random.Random(seed)
    # NOTE: only random() is called, the one method Python keeps stable across versions for a seed
    return {
        group: Fraction(generator.random())
        * Fraction(group_frame_count, group_to_allocation[group])
        for group, group_frame_count in group_to_frame_count.items()
    }


def get_group_positions(
    frame_count: int, allocation: int, start: Fraction
) -> list[int]:
    interval = Fraction(frame_count, allocation)
    return [
        math.floor(start + pick_index * interval) for pick_index in range(allocation)
    ]


def get_drawn_rows(
    group_to_speech_ids: dict[str, list[int]],
    group_to_allocation: dict[str, int],
    group_to_start: dict[str, Fraction],
) -> list[DrawnRow]:
    drawn_rows = []
    group_offset = 0
    for group, speech_ids in group_to_speech_ids.items():
        for position in get_group_positions(
            len(speech_ids), group_to_allocation[group], group_to_start[group]
        ):
            drawn_rows.append(
                DrawnRow(
                    speech_id=speech_ids[position],
                    group=group,
                    frame_position=group_offset + position,
                )
            )
        group_offset += len(speech_ids)
    return drawn_rows


def get_speech_id_to_next_row(
    neighbour_rows: list[SpeechParseRow],
) -> dict[int, SpeechParseRow]:
    return {
        current_row.id: next_row
        for current_row, next_row in pairwise(neighbour_rows)
        if current_row.report_id == next_row.report_id
    }


def build_snapshot_row(
    speech_snapshot_row: SpeechSnapshotRow,
    next_row: Optional[SpeechParseRow],
    speaker_id_to_speaker: dict[int, Speaker],
    person_id_to_canonical_name: dict[Optional[int], str],
) -> HandCheckSnapshotRow:
    if speech_snapshot_row.speaker_id is None:
        raise HansardHandCheckError(
            f"Drawn speech {speech_snapshot_row.id} holds no speaker id"
        )
    speaker = speaker_id_to_speaker[speech_snapshot_row.speaker_id]
    return HandCheckSnapshotRow(
        speech_id=speech_snapshot_row.id,
        report_id=speech_snapshot_row.report_id,
        hansard_report_id=speech_snapshot_row.hansard_report_id,
        html_file_name=speech_snapshot_row.html_file_name,
        report_version=speech_snapshot_row.report_version,
        report_type=speech_snapshot_row.report_type,
        parliament_number=speech_snapshot_row.parliament_number,
        sitting_date=speech_snapshot_row.sitting_date,
        report_title=speech_snapshot_row.title,
        ordinal=speech_snapshot_row.ordinal,
        speaker=speech_snapshot_row.speaker,
        speaker_id=speech_snapshot_row.speaker_id,
        speaker_name=speaker.name,
        person_name=person_id_to_canonical_name.get(speaker.person_id),
        kind=speech_snapshot_row.kind,
        transcript=speech_snapshot_row.transcript,
        next_speaker=None if next_row is None else next_row.speaker,
        next_transcript=None if next_row is None else next_row.transcript,
    )


def get_draw_tsv_lines(drawn_rows: list[DrawnRow]) -> list[str]:
    return [
        _DRAW_TSV_HEADER,
        *(
            f"{drawn_row.speech_id}\t{drawn_row.group}\t{drawn_row.frame_position}"
            for drawn_row in drawn_rows
        ),
    ]


def get_summary_lines(frame_summary: HandCheckFrameSummary) -> list[str]:
    return [
        f"database_label: {frame_summary.database_label}",
        f"read_at: {frame_summary.read_at.isoformat()}",
        f"seed: {frame_summary.seed}",
        f"sample_size: {frame_summary.sample_size}",
        f"frame_hash: {frame_summary.frame_hash}",
        f"weight_spread: {frame_summary.weight_spread}",
        "group\tframe_count\tallocation\tstart",
        *(
            f"{group}\t{group_frame_count}\t{frame_summary.group_to_allocation[group]}\t{frame_summary.group_to_start[group]}"
            for group, group_frame_count in frame_summary.group_to_frame_count.items()
        ),
    ]


def write_draw_files(
    is_pilot: bool,
    snapshot_directory: Path,
    record_directory: Path,
    snapshot_text: str,
    draw_tsv_text: str,
    summary_text: str,
) -> None:
    # NOTE: a main draw opens each file with "x", so a second one cannot replace the frozen snapshot; the pilot is rerun on purpose and overwrites
    write_mode = "w" if is_pilot else "x"
    snapshot_directory.mkdir(parents=True, exist_ok=True)
    record_directory.mkdir(parents=True, exist_ok=True)
    for file_path, text in (
        (snapshot_directory / _SNAPSHOT_FILE_NAME, snapshot_text),
        (record_directory / _DRAW_TSV_FILE_NAME, draw_tsv_text),
        (record_directory / _SUMMARY_FILE_NAME, summary_text),
    ):
        with file_path.open(write_mode, encoding="utf-8") as output_file:
            output_file.write(text)


def draw_hand_check_sample(
    is_pilot: bool, snapshot_directory: Path, record_directory: Path
) -> None:
    seed = _PILOT_SEED if is_pilot else _MAIN_SEED
    sample_size = _PILOT_SAMPLE_SIZE if is_pilot else _MAIN_SAMPLE_SIZE
    database_label = get_database_label(settings.database_url)
    logger.info(f"Drawing {sample_size} rows, read only, from {database_label}")
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_DRAW_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        read_at = datetime.now(timezone.utc)
        frame = read_frame(CRUDSpeech(session).get_frame_rows_by_speaker_id_not_null())
        group_to_frame_count = {
            group: len(speech_ids)
            for group, speech_ids in frame.group_to_speech_ids.items()
        }
        group_to_allocation = get_allocation(group_to_frame_count, sample_size)
        weight_spread = get_weight_spread(group_to_frame_count, group_to_allocation)
        validate_can_write_draw(
            group_to_allocation, sample_size, weight_spread, is_pilot
        )
        group_to_start = get_group_to_start(
            group_to_frame_count, group_to_allocation, seed
        )
        drawn_rows = get_drawn_rows(
            frame.group_to_speech_ids, group_to_allocation, group_to_start
        )
        speech_snapshot_rows = CRUDSpeech(session).get_snapshot_rows_by_ids(
            [drawn_row.speech_id for drawn_row in drawn_rows]
        )
        report_ids = {
            speech_snapshot_row.report_id
            for speech_snapshot_row in speech_snapshot_rows
        }
        neighbour_rows = CRUDSpeech(session).get_parse_rows_by_report_ids(
            list(report_ids)
        )
        speaker_id_to_speaker = {
            speaker.id: speaker
            for speaker in CRUDSpeaker(session).get_all()
            if speaker.id is not None
        }
        person_id_to_canonical_name = {
            person.id: person.canonical_name for person in CRUDPerson(session).get_all()
        }

    speech_id_to_speech_snapshot_row = {
        speech_snapshot_row.id: speech_snapshot_row
        for speech_snapshot_row in speech_snapshot_rows
    }
    speech_id_to_next_row = get_speech_id_to_next_row(neighbour_rows)
    snapshot_rows = [
        build_snapshot_row(
            speech_id_to_speech_snapshot_row[drawn_row.speech_id],
            speech_id_to_next_row.get(drawn_row.speech_id),
            speaker_id_to_speaker,
            person_id_to_canonical_name,
        )
        for drawn_row in drawn_rows
    ]
    frame_summary = HandCheckFrameSummary(
        database_label=database_label,
        read_at=read_at,
        seed=seed,
        sample_size=sample_size,
        group_to_frame_count=group_to_frame_count,
        group_to_allocation=group_to_allocation,
        group_to_start={group: str(start) for group, start in group_to_start.items()},
        frame_hash=frame.frame_hash,
        weight_spread=str(weight_spread),
    )
    summary_lines = get_summary_lines(frame_summary)

    write_draw_files(
        is_pilot,
        snapshot_directory,
        record_directory,
        HandCheckSnapshot(frame=frame_summary, rows=snapshot_rows).model_dump_json(
            indent=1
        ),
        "\n".join(get_draw_tsv_lines(drawn_rows)) + "\n",
        "\n".join(summary_lines) + "\n",
    )
    for line in summary_lines:
        logger.info(line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Draw the human hand check sample from the database, read only, and write the snapshot and the draw record"
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="draw the 20-row pilot with the pilot seed instead of the 1,000-row main sample",
    )
    parser.add_argument(
        "--snapshot-directory",
        type=Path,
        required=True,
        help="write snapshot.json here, such as plans/hand-check/main",
    )
    parser.add_argument(
        "--record-directory",
        type=Path,
        required=True,
        help="write draw.tsv and draw-summary.txt here, such as docs/report/hand-check",
    )
    arguments = parser.parse_args()
    draw_hand_check_sample(
        arguments.pilot, arguments.snapshot_directory, arguments.record_directory
    )
