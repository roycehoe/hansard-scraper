import argparse
import hashlib
from collections.abc import Hashable
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.report import CRUDReport, ReportFrameRow
from database.init import build_read_only_engine
from enums import ParticipantRole, QuestionState
from exceptions import HansardHandCheckError
from logs import logger
from schemas.pq_roles_round_one_row import PqRolesRoundOneRow
from scripts.draw_hand_check_sample import (
    get_allocation,
    get_group_positions,
    get_group_to_start,
    get_weight_spread,
    validate_can_write_draw,
)
from services.attribution import get_group
from settings import settings
from utils.database_label import get_database_label

LATER_ANSWERER_FRAME = "LATER_ANSWERER"
NO_ANSWER_FRAME = "NO_ANSWER"
# NOTE: the list order fixes each frame's seed, _FIRST_SEED plus its index
_FRAME_NAMES = (
    ParticipantRole.ASKER.value,
    ParticipantRole.ABSENT_FILER.value,
    ParticipantRole.READER.value,
    ParticipantRole.ASKER_FOLLOW_UP.value,
    ParticipantRole.SUPPLEMENTARY.value,
    ParticipantRole.ANSWERER.value,
    ParticipantRole.CHAIR.value,
    ParticipantRole.UNLABELLED.value,
    QuestionState.NOT_A_QUESTION.value,
    QuestionState.NOT_ASKED_ALOUD.value,
    QuestionState.CORRECTION.value,
    QuestionState.URGENT.value,
    LATER_ANSWERER_FRAME,
    NO_ANSWER_FRAME,
)
_FIRST_SEED = 20_261_141
_PLANT_SEED = 20_261_161
_BASE_SAMPLE_SIZE = 200
_LATER_ANSWERER_MINIMUM_RANK = 2
_MAX_WEIGHT_SPREAD = Fraction(3, 100)
_ALLOWED_DATABASE_LABEL = "localhost:5435/hansard_asked_by"
_DRAW_ISOLATION_LEVEL = "REPEATABLE READ"
_OUTPUT_DIRECTORY = Path(
    "/Users/meinhardt/ghq/github.com/roycehoe/hansard/plans/pq-roles-evidence/round2/draw"
)
_ROUND_ONE_SAMPLE_PATH = Path(
    "/Users/meinhardt/ghq/github.com/roycehoe/hansard/plans/pq-roles-sample/sample.jsonl"
)
_DRAW_TSV_FILE_NAME = "draw.tsv"
_SUMMARY_FILE_NAME = "draw-summary.txt"
_DRAW_TSV_HEADER = "frame\trow_id\treport_id\tgroup\tframe_position"


@dataclass(frozen=True)
class Frame:
    name: str
    seed: int
    rows: list[ReportFrameRow]
    group_to_rows: dict[str, list[ReportFrameRow]]
    frame_hash: str


@dataclass(frozen=True)
class Pick:
    group: str
    position: int
    row: ReportFrameRow


@dataclass(frozen=True)
class FrameDraw:
    frame: Frame
    sample_size: int
    raise_reason: Optional[str]
    is_whole: bool
    group_to_allocation: dict[str, int]
    group_to_start: dict[str, Fraction]
    weight_spread: Fraction
    picks: list[Pick]
    move_count: int
    repeat_count: int


def get_frame_seed(frame_name: str) -> int:
    return _FIRST_SEED + _FRAME_NAMES.index(frame_name)


def _get_frame_sort_key(row: ReportFrameRow) -> tuple[Hashable, ...]:
    return (
        row.parliament_number,
        row.report_version,
        row.report_type,
        row.sitting_date,
        row.sprs_report_id,
        0 if row.first_ordinal is None else row.first_ordinal,
        row.id,
    )


def validate_can_draw_frame_order(frame_name: str, rows: list[ReportFrameRow]) -> None:
    # NOTE: Python compares ASCII strings by code point, which is the byte order the database's COLLATE "C" gives
    for previous_row, row in pairwise(rows):
        if _get_frame_sort_key(previous_row) >= _get_frame_sort_key(row):
            raise HansardHandCheckError(
                f"Refusing to draw: frame {frame_name} is out of order or repeats a row at id {previous_row.id} then {row.id}"
            )


def validate_can_draw_from(database_label: str) -> None:
    if database_label != _ALLOWED_DATABASE_LABEL:
        raise HansardHandCheckError(
            f"Refusing to draw from {database_label}, only {_ALLOWED_DATABASE_LABEL}"
        )


def build_frame(frame_name: str, rows: list[ReportFrameRow]) -> Frame:
    validate_can_draw_frame_order(frame_name, rows)
    group_to_rows: dict[str, list[ReportFrameRow]] = {}
    frame_hasher = hashlib.sha256()
    for row in rows:
        group_to_rows.setdefault(get_group(row.parliament_number), []).append(row)
        frame_hasher.update(f"{row.id}\n".encode("ascii"))
    return Frame(
        name=frame_name,
        seed=get_frame_seed(frame_name),
        rows=rows,
        group_to_rows=group_to_rows,
        frame_hash=frame_hasher.hexdigest(),
    )


def get_frame_rows(session: Session, frame_name: str) -> list[ReportFrameRow]:
    if frame_name == LATER_ANSWERER_FRAME:
        return CRUDReport(
            session
        ).get_frame_rows_by_participant_role_and_first_ordinal_above_report_minimum(
            ParticipantRole.ANSWERER
        )
    if frame_name == NO_ANSWER_FRAME:
        return CRUDReport(
            session
        ).get_frame_rows_by_participant_roles_present_and_participant_role_absent_and_question_state_absent(
            [ParticipantRole.ASKER, ParticipantRole.ABSENT_FILER],
            ParticipantRole.ANSWERER,
        )
    if frame_name in QuestionState:
        return CRUDReport(session).get_frame_rows_by_question_state(
            QuestionState(frame_name)
        )
    return CRUDReport(session).get_frame_rows_by_participant_role(
        ParticipantRole(frame_name)
    )


def _get_spread_or_none(
    group_to_frame_count: dict[str, int], group_to_allocation: dict[str, int]
) -> Optional[Fraction]:
    if min(group_to_allocation.values()) == 0:
        return None
    return get_weight_spread(group_to_frame_count, group_to_allocation)


def get_sample_size(group_to_frame_count: dict[str, int]) -> tuple[int, Optional[str]]:
    """Return the sample size and, when it was raised past the base size, why."""
    frame_count = sum(group_to_frame_count.values())
    if frame_count <= _BASE_SAMPLE_SIZE:
        return frame_count, None
    base_allocation = get_allocation(group_to_frame_count, _BASE_SAMPLE_SIZE)
    base_spread = _get_spread_or_none(group_to_frame_count, base_allocation)
    if base_spread is not None and base_spread <= _MAX_WEIGHT_SPREAD:
        return _BASE_SAMPLE_SIZE, None
    # NOTE: at the frame count every group's allocation is its own count, so the weights are equal and the search always ends
    for sample_size in range(_BASE_SAMPLE_SIZE + 1, frame_count + 1):
        group_to_allocation = get_allocation(group_to_frame_count, sample_size)
        spread = _get_spread_or_none(group_to_frame_count, group_to_allocation)
        if spread is not None and spread <= _MAX_WEIGHT_SPREAD:
            reason = (
                "the weights spread by too much at 200"
                if base_spread is None
                else f"the weights spread by {float(base_spread):.4f} at 200"
            )
            return sample_size, f"raised from 200 to {sample_size}: {reason}"
    raise HansardHandCheckError(
        f"Refusing to draw: no sample size up to {frame_count} meets the weight limit"
    )


def get_distinct_report_picks(
    group_rows: list[ReportFrameRow], positions: list[int]
) -> tuple[list[int], int, int]:
    """Return the picked positions, how many moved and how many repeat a report."""
    drawn_report_ids: set[int] = set()
    picked_positions: set[int] = set()
    move_count = 0
    repeat_count = 0
    for position in positions:
        scan_order = [
            (position + step) % len(group_rows) for step in range(len(group_rows))
        ]
        if (
            group_rows[position].report_id not in drawn_report_ids
            and position not in picked_positions
        ):
            chosen_position = position
        else:
            distinct_positions = [
                candidate
                for candidate in scan_order
                if candidate not in picked_positions
                and group_rows[candidate].report_id not in drawn_report_ids
            ]
            if distinct_positions:
                chosen_position = distinct_positions[0]
                move_count += 1
            else:
                chosen_position = next(
                    candidate
                    for candidate in scan_order
                    if candidate not in picked_positions
                )
                repeat_count += 1
        picked_positions.add(chosen_position)
        drawn_report_ids.add(group_rows[chosen_position].report_id)
    return sorted(picked_positions), move_count, repeat_count


def draw_frame(frame: Frame) -> FrameDraw:
    group_to_frame_count = {
        group: len(rows) for group, rows in frame.group_to_rows.items()
    }
    sample_size, raise_reason = get_sample_size(group_to_frame_count)
    group_to_allocation = get_allocation(group_to_frame_count, sample_size)
    if sample_size == len(frame.rows):
        group_offset = 0
        picks = []
        for group, group_rows in frame.group_to_rows.items():
            picks.extend(
                Pick(group=group, position=group_offset + index, row=row)
                for index, row in enumerate(group_rows)
            )
            group_offset += len(group_rows)
        return FrameDraw(
            frame=frame,
            sample_size=sample_size,
            raise_reason=raise_reason,
            is_whole=True,
            group_to_allocation=group_to_allocation,
            group_to_start={},
            weight_spread=Fraction(0),
            picks=picks,
            move_count=0,
            repeat_count=0,
        )
    weight_spread = get_weight_spread(group_to_frame_count, group_to_allocation)
    validate_can_write_draw(group_to_allocation, sample_size, weight_spread, False)
    group_to_start = get_group_to_start(
        group_to_frame_count, group_to_allocation, frame.seed
    )
    picks = []
    move_count = 0
    repeat_count = 0
    group_offset = 0
    for group, group_rows in frame.group_to_rows.items():
        positions, group_move_count, group_repeat_count = get_distinct_report_picks(
            group_rows,
            get_group_positions(
                len(group_rows), group_to_allocation[group], group_to_start[group]
            ),
        )
        picks.extend(
            Pick(
                group=group, position=group_offset + position, row=group_rows[position]
            )
            for position in positions
        )
        move_count += group_move_count
        repeat_count += group_repeat_count
        group_offset += len(group_rows)
    return FrameDraw(
        frame=frame,
        sample_size=sample_size,
        raise_reason=raise_reason,
        is_whole=False,
        group_to_allocation=group_to_allocation,
        group_to_start=group_to_start,
        weight_spread=weight_spread,
        picks=picks,
        move_count=move_count,
        repeat_count=repeat_count,
    )


def _get_match_key(frame_name: str, row: ReportFrameRow) -> Hashable:
    if frame_name in QuestionState or frame_name == NO_ANSWER_FRAME:
        return row.report_id
    person = row.speaker_id if row.speaker_id is not None else row.printed_name
    return (row.report_id, person)


def get_round_one_keys(
    frame_name: str, round_one_rows: list[PqRolesRoundOneRow]
) -> set[Hashable]:
    if frame_name == NO_ANSWER_FRAME:
        return {row.report_id for row in round_one_rows if row.kind == "question"}
    if frame_name in QuestionState:
        return {
            row.report_id
            for row in round_one_rows
            if row.kind == "state" and row.state == frame_name
        }
    role = (
        ParticipantRole.ANSWERER.value
        if frame_name == LATER_ANSWERER_FRAME
        else frame_name
    )
    return {
        (
            row.report_id,
            row.speaker_id if row.speaker_id is not None else row.printed_name,
        )
        for row in round_one_rows
        if row.kind == "participant"
        and row.role == role
        and (
            frame_name != LATER_ANSWERER_FRAME
            or (
                row.answerer_rank is not None
                and row.answerer_rank >= _LATER_ANSWERER_MINIMUM_RANK
            )
        )
    }


def count_round_one_matches(
    frame_name: str, picks: list[Pick], round_one_rows: list[PqRolesRoundOneRow]
) -> int:
    round_one_keys = get_round_one_keys(frame_name, round_one_rows)
    return sum(
        1 for pick in picks if _get_match_key(frame_name, pick.row) in round_one_keys
    )


def get_draw_tsv_lines(frame_draws: list[FrameDraw]) -> list[str]:
    return [
        _DRAW_TSV_HEADER,
        *(
            f"{frame_draw.frame.name}\t{pick.row.id}\t{pick.row.report_id}\t{pick.group}\t{pick.position}"
            for frame_draw in frame_draws
            for pick in frame_draw.picks
        ),
    ]


def get_summary_lines(
    frame_draw: FrameDraw, database_label: str, read_at: datetime, match_count: int
) -> list[str]:
    frame = frame_draw.frame
    return [
        f"frame: {frame.name}",
        f"database_label: {database_label}",
        f"read_at: {read_at.isoformat()}",
        f"seed: {'none, taken whole' if frame_draw.is_whole else frame.seed}",
        f"frame_count: {len(frame.rows)}",
        f"frame_hash: {frame.frame_hash}",
        f"sample_size: {frame_draw.sample_size}"
        + ("" if frame_draw.raise_reason is None else f" ({frame_draw.raise_reason})"),
        f"weight_spread: {frame_draw.weight_spread}",
        f"moves: {frame_draw.move_count}",
        f"repeats: {frame_draw.repeat_count}",
        f"round_one_matches: {match_count}",
        "group\tframe_count\tallocation\tstart",
        *(
            f"{group}\t{len(group_rows)}\t{frame_draw.group_to_allocation[group]}\t{frame_draw.group_to_start.get(group, '')}"
            for group, group_rows in frame.group_to_rows.items()
        ),
        "",
    ]


def write_draw_files(draw_tsv_text: str, summary_text: str) -> None:
    # NOTE: each file opens with "x", so a second run cannot replace the first draw
    _OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for file_name, text in (
        (_DRAW_TSV_FILE_NAME, draw_tsv_text),
        (_SUMMARY_FILE_NAME, summary_text),
    ):
        with (_OUTPUT_DIRECTORY / file_name).open("x", encoding="utf-8") as output_file:
            output_file.write(text)


def draw_pq_roles_sample() -> None:
    database_label = get_database_label(settings.database_url)
    validate_can_draw_from(database_label)
    logger.info(f"Drawing the PQ roles frames, read only, from {database_label}")
    round_one_rows = [
        PqRolesRoundOneRow.model_validate_json(line)
        for line in _ROUND_ONE_SAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    ]
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_DRAW_ISOLATION_LEVEL
    )
    frame_draws = []
    with Session(read_only_engine) as session:
        read_at = datetime.now(timezone.utc)
        frames = [
            build_frame(frame_name, get_frame_rows(session, frame_name))
            for frame_name in _FRAME_NAMES
        ]
    for frame in frames:
        frame_draws.append(draw_frame(frame))
    summary_lines = [
        line
        for frame_draw in frame_draws
        for line in get_summary_lines(
            frame_draw,
            database_label,
            read_at,
            count_round_one_matches(
                frame_draw.frame.name, frame_draw.picks, round_one_rows
            ),
        )
    ]
    write_draw_files(
        "\n".join(get_draw_tsv_lines(frame_draws)) + "\n",
        "\n".join(summary_lines) + "\n",
    )
    for line in summary_lines:
        logger.info(line)


if __name__ == "__main__":
    argparse.ArgumentParser(
        description="Draw the PQ roles round 2 hand check sample, read only, from hansard_asked_by"
    ).parse_args()
    draw_pq_roles_sample()
