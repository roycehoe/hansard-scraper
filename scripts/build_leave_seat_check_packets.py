import argparse
import hashlib
import random
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from fractions import Fraction
from itertools import pairwise
from math import ceil
from pathlib import Path
from typing import Optional

from pydantic import TypeAdapter
from sqlmodel import Session

from crud.leave_period_printing import (
    CRUDLeavePeriodPrinting,
    LeavePeriodPrintingCheckRow,
)
from crud.seat_holding import CRUDSeatHolding, SeatHoldingCheckRow
from database.init import build_read_only_engine
from enums import LeaveEntryFormat, LeaveNameSource, LeaveYearSource
from exceptions import HansardHandCheckError
from logs import logger
from schemas.leave_seat_check import LeaveSeatCheckKeyEntry, LeaveSeatCheckPacket
from settings import settings
from utils.database_label import get_database_label
from utils.leave_entry import YEAR_ORDER_BREAK_GROUP, get_leave_gap_days

_ALLOWED_DATABASE_LABEL = "localhost:5437/hansard_positions"
_DRAW_ISOLATION_LEVEL = "REPEATABLE READ"
_SAMPLE_SIZE = 50
_PLANT_SHARE = Fraction(1, 10)
_MINIMUM_PLANTS = 1
_YEAR_GAP_NEAR_DAYS = 30
_YEAR_GAP_FAR_DAYS = 90
_YEARS_IN_DECADE = 10
_FEBRUARY = 2
_LAST_DAY_OF_FEBRUARY = 28
_LEAVE_TABLE_NAME = "leave_period_printing"
_SEAT_TABLE_NAME = "seat_holding"
_GROUP_SEPARATOR = "|"
_NONE_TEXT = "(none)"
_BLANK_NAME_TEXT = "(blank)"
_YEAR_RE = re.compile(r"\d{4}")
_GAP_BAND_ZERO = "0"
_GAP_BAND_NEAR = "1-30"
_GAP_BAND_FAR = "31-90"
_GAP_BAND_OVER = "over-90"
_FORMAT_FAMILY = "format"
_YEAR_GAP_FAMILY = "year_gap"
_HEADING_YEAR_GAP_FAMILY = "heading_year_gap"
_YEAR_OUTSIDE_HEADING_FAMILY = "year_outside_heading"
_CARRIED_FAMILY = "carried"
_LINK_FAMILY = "link"
_OFFICE_FAMILY = "office"
_SHARED_LINE_FAMILY = "shared_line"
_SEAT_FAMILY = "seat"
_PACKETS_FILE_NAME = "packets.jsonl"
_KEY_FILE_NAME = "key.json"
_KEY_HASH_FILE_NAME = "key.sha256"
_DRAW_TSV_FILE_NAME = "draw.tsv"
_SUMMARY_FILE_NAME = "draw-summary.txt"
_DRAW_TSV_HEADER = "group\ttable\trow_id\tis_plant"
_RULE_FORMAT = "The row's entry format is the one the reader assigned from the printed line, and the name, dates and office follow from it."
_RULE_YEAR_GAP = "The list prints no year. The stored start date is the printed day and month in the year nearest the sitting, and the gap to the sitting is as stated."
_RULE_HEADING_YEAR_GAP = "The year comes from the printed column heading. The stored start date is the printed day and month in that year."
_RULE_YEAR_OUTSIDE_HEADING = "The stored year is the one nearest the sitting. Check that it matches the years the printed column headings give."
_RULE_CARRIED = "A blank printed name takes the name of the nearest named row above it in the same list."
_RULE_LINK = "The linked member is the one whose name equals the printed or carried name exactly, or whose attendance entry prints that name."
_RULE_OFFICE = (
    "The office is the one the sitting's attendance list prints for the linked member."
)
_RULE_SHARED_LINE = "One printed line makes several rows. Each row takes its own name and dates from that line."
_RULE_YEAR_ORDER_BREAK = "The list names a member in a row below a row with a later start date. Check each stored start date against the printed day and month."
_RULE_SEAT = "The seat row spans the first to the last sitting at which the member's attendance entry printed this division."
_RULE_NONE = "Check the stored values against the source text."


@dataclass(frozen=True)
class CheckItem:
    table_name: str
    row_id: int
    source_text: str
    name: Optional[str]
    member: Optional[str]
    office: Optional[str]
    start_date: Optional[date]
    other_says: str


@dataclass(frozen=True)
class Plant:
    item: CheckItem
    note: str


@dataclass(frozen=True)
class GroupDraw:
    group: str
    frame_count: int
    sample: list[CheckItem]
    plants: list[Plant]
    skipped_plant_count: int


@dataclass(frozen=True)
class PacketEntry:
    packet: LeaveSeatCheckPacket
    key_entry: LeaveSeatCheckKeyEntry


_KEY_ADAPTER = TypeAdapter(list[LeaveSeatCheckKeyEntry])


def _validate_can_draw_from(database_label: str) -> None:
    if database_label != _ALLOWED_DATABASE_LABEL:
        raise HansardHandCheckError(
            f"Refusing to draw from {database_label}, only {_ALLOWED_DATABASE_LABEL}"
        )


def _get_decade(day: date) -> int:
    return day.year // _YEARS_IN_DECADE * _YEARS_IN_DECADE


def _get_gap_band(gap_days: int) -> str:
    if gap_days == 0:
        return _GAP_BAND_ZERO
    if gap_days <= _YEAR_GAP_NEAR_DAYS:
        return _GAP_BAND_NEAR
    if gap_days <= _YEAR_GAP_FAR_DAYS:
        return _GAP_BAND_FAR
    return _GAP_BAND_OVER


def _is_year_outside_heading(check_row: LeavePeriodPrintingCheckRow) -> bool:
    if check_row.year_source != LeaveYearSource.NEAREST_TO_SITTING:
        return False
    if check_row.start_date is None:
        return False
    start_heading_years = _YEAR_RE.findall(check_row.printed_heading_from or "")
    if not start_heading_years:
        return False
    if str(check_row.start_date.year) not in start_heading_years:
        return True
    end_heading_years = _YEAR_RE.findall(check_row.printed_heading_to or "")
    if not end_heading_years:
        return False
    if check_row.end_date is None:
        return False
    return str(check_row.end_date.year) not in end_heading_years


def get_leave_printing_groups(check_row: LeavePeriodPrintingCheckRow) -> list[str]:
    decade = _get_decade(check_row.sitting_date)
    groups = [
        _GROUP_SEPARATOR.join(
            [_FORMAT_FAMILY, str(check_row.entry_format), str(decade)]
        )
    ]
    if check_row.start_date is not None:
        gap_band = _get_gap_band(
            get_leave_gap_days(
                check_row.start_date, check_row.end_date, check_row.sitting_date
            )
        )
        if check_row.year_source == LeaveYearSource.NEAREST_TO_SITTING:
            groups.append(_GROUP_SEPARATOR.join([_YEAR_GAP_FAMILY, gap_band]))
        if check_row.year_source == LeaveYearSource.PRINTED_COLUMN_HEADING:
            groups.append(_GROUP_SEPARATOR.join([_HEADING_YEAR_GAP_FAMILY, gap_band]))
    if _is_year_outside_heading(check_row):
        groups.append(_YEAR_OUTSIDE_HEADING_FAMILY)
    if check_row.name_source == LeaveNameSource.CARRIED_FROM_ROW_ABOVE:
        groups.append(
            _GROUP_SEPARATOR.join(
                [_CARRIED_FAMILY, str(check_row.entry_format), str(decade)]
            )
        )
    if check_row.speaker_link_source is not None:
        groups.append(
            _GROUP_SEPARATOR.join(
                [_LINK_FAMILY, str(check_row.speaker_link_source), str(decade)]
            )
        )
    if check_row.office_source is not None:
        groups.append(
            _GROUP_SEPARATOR.join(
                [_OFFICE_FAMILY, str(check_row.office_source), str(decade)]
            )
        )
    return groups


def get_seat_holding_group(check_row: SeatHoldingCheckRow) -> str:
    return _GROUP_SEPARATOR.join(
        [_SEAT_FAMILY, str(_get_decade(check_row.first_sitting_date))]
    )


def get_shared_line_row_ids(
    check_rows: list[LeavePeriodPrintingCheckRow],
) -> set[int]:
    sitting_id_and_line_to_row_ids: dict[tuple[int, str], list[int]] = {}
    for check_row in check_rows:
        if check_row.entry_format == LeaveEntryFormat.TABLE_ROW:
            continue
        if check_row.printed_line is None:
            continue
        sitting_id_and_line_to_row_ids.setdefault(
            (check_row.sitting_id, check_row.printed_line), []
        ).append(check_row.id)
    return {
        row_id
        for row_ids in sitting_id_and_line_to_row_ids.values()
        if len(row_ids) > 1
        for row_id in row_ids
    }


def get_order_break_sitting_ids(
    check_rows: list[LeavePeriodPrintingCheckRow],
) -> set[int]:
    sitting_id_to_rows: dict[int, list[LeavePeriodPrintingCheckRow]] = {}
    for check_row in check_rows:
        if check_row.entry_format != LeaveEntryFormat.STRUCTURED_LIST:
            continue
        sitting_id_to_rows.setdefault(check_row.sitting_id, []).append(check_row)
    order_break_sitting_ids = set()
    for sitting_id, sitting_rows in sitting_id_to_rows.items():
        ordered_rows = sorted(sitting_rows, key=lambda sitting_row: sitting_row.ordinal)
        for row_above, check_row in pairwise(ordered_rows):
            if check_row.name_source != LeaveNameSource.CARRIED_FROM_ROW_ABOVE:
                continue
            if check_row.start_date is None:
                continue
            if row_above.start_date is None:
                continue
            if check_row.start_date < row_above.start_date:
                order_break_sitting_ids.add(sitting_id)
    return order_break_sitting_ids


def _get_leave_source_text(check_row: LeavePeriodPrintingCheckRow) -> str:
    if check_row.printed_line is not None:
        return check_row.printed_line
    return (
        f"{check_row.printed_name or _BLANK_NAME_TEXT} | {check_row.printed_from or ''}"
        f" | {check_row.printed_to or ''} | {check_row.printed_heading_from or ''}"
        f" / {check_row.printed_heading_to or ''}"
    )


def _get_shown_text(value: object) -> str:
    if value is None:
        return _NONE_TEXT
    return str(value)


def _build_leave_item(check_row: LeavePeriodPrintingCheckRow) -> CheckItem:
    return CheckItem(
        table_name=_LEAVE_TABLE_NAME,
        row_id=check_row.id,
        source_text=_get_leave_source_text(check_row),
        name=check_row.printed_name or check_row.carried_name,
        member=check_row.speaker_name,
        office=check_row.office_printed,
        start_date=check_row.start_date,
        other_says=(
            f"end: {_get_shown_text(check_row.end_date)}; end text: {_get_shown_text(check_row.end_text)};"
            f" name source: {check_row.name_source}; year source: {_get_shown_text(check_row.year_source)};"
            f" link source: {_get_shown_text(check_row.speaker_link_source)};"
            f" office source: {_get_shown_text(check_row.office_source)}"
        ),
    )


def _build_seat_item(check_row: SeatHoldingCheckRow) -> CheckItem:
    return CheckItem(
        table_name=_SEAT_TABLE_NAME,
        row_id=check_row.id,
        source_text=(
            f"{check_row.location_name} | {check_row.speaker_name}"
            f" | first sitting {check_row.first_sitting_date}"
            f" | last sitting {check_row.last_sitting_date}"
        ),
        name=None,
        member=check_row.speaker_name,
        office=None,
        start_date=check_row.first_sitting_date,
        other_says=(
            f"division: {check_row.division_key}; last sitting: {check_row.last_sitting_date};"
            f" sittings: {check_row.sitting_count}"
        ),
    )


def _get_data_says(item: CheckItem) -> str:
    if item.table_name == _SEAT_TABLE_NAME:
        return f"member: {_get_shown_text(item.member)}; first sitting: {_get_shown_text(item.start_date)}; {item.other_says}"
    return (
        f"name: {_get_shown_text(item.name)}; member: {_get_shown_text(item.member)};"
        f" office: {_get_shown_text(item.office)}; start: {_get_shown_text(item.start_date)}; {item.other_says}"
    )


def get_group_to_items(
    leave_check_rows: list[LeavePeriodPrintingCheckRow],
    seat_check_rows: list[SeatHoldingCheckRow],
) -> dict[str, list[CheckItem]]:
    group_to_items: dict[str, list[CheckItem]] = {}
    shared_line_row_ids = get_shared_line_row_ids(leave_check_rows)
    order_break_sitting_ids = get_order_break_sitting_ids(leave_check_rows)
    for check_row in leave_check_rows:
        item = _build_leave_item(check_row)
        groups = get_leave_printing_groups(check_row)
        if check_row.id in shared_line_row_ids:
            groups.append(
                _GROUP_SEPARATOR.join(
                    [_SHARED_LINE_FAMILY, str(_get_decade(check_row.sitting_date))]
                )
            )
        if check_row.sitting_id in order_break_sitting_ids:
            groups.append(YEAR_ORDER_BREAK_GROUP)
        for group in groups:
            group_to_items.setdefault(group, []).append(item)
    for seat_check_row in seat_check_rows:
        group_to_items.setdefault(get_seat_holding_group(seat_check_row), []).append(
            _build_seat_item(seat_check_row)
        )
    return group_to_items


def _get_rule_text(group: str) -> str:
    family = group.partition(_GROUP_SEPARATOR)[0]
    if family == _FORMAT_FAMILY:
        return _RULE_FORMAT
    if family == _YEAR_GAP_FAMILY:
        return _RULE_YEAR_GAP
    if family == _HEADING_YEAR_GAP_FAMILY:
        return _RULE_HEADING_YEAR_GAP
    if family == _YEAR_OUTSIDE_HEADING_FAMILY:
        return _RULE_YEAR_OUTSIDE_HEADING
    if family == _CARRIED_FAMILY:
        return _RULE_CARRIED
    if family == _LINK_FAMILY:
        return _RULE_LINK
    if family == _OFFICE_FAMILY:
        return _RULE_OFFICE
    if family == _SHARED_LINE_FAMILY:
        return _RULE_SHARED_LINE
    if family == YEAR_ORDER_BREAK_GROUP:
        return _RULE_YEAR_ORDER_BREAK
    if family == _SEAT_FAMILY:
        return _RULE_SEAT
    return _RULE_NONE


def get_plant_count(sample_size: int) -> int:
    return max(_MINIMUM_PLANTS, ceil(sample_size * _PLANT_SHARE))


def _get_next_year(day: date) -> date:
    try:
        return day.replace(year=day.year + 1)
    except ValueError:
        return date(day.year + 1, _FEBRUARY, _LAST_DAY_OF_FEBRUARY)


def _get_plant(
    item: CheckItem,
    group: str,
    group_items: list[CheckItem],
    generator: random.Random,
) -> Optional[Plant]:
    family = group.partition(_GROUP_SEPARATOR)[0]
    if family == _CARRIED_FAMILY:
        names = sorted(
            {
                other_item.name
                for other_item in group_items
                if other_item.name is not None and other_item.name != item.name
            }
        )
        if not names:
            return None
        name = generator.choice(names)
        return Plant(
            replace(item, name=name),
            f"replaced the name {_get_shown_text(item.name)} with {name}",
        )
    if family == _LINK_FAMILY:
        members = sorted(
            {
                other_item.member
                for other_item in group_items
                if other_item.member is not None and other_item.member != item.member
            }
        )
        if not members:
            return None
        member = generator.choice(members)
        return Plant(
            replace(item, member=member),
            f"replaced the linked member {_get_shown_text(item.member)} with {member}",
        )
    if family == _OFFICE_FAMILY:
        offices = sorted(
            {
                other_item.office
                for other_item in group_items
                if other_item.office is not None and other_item.office != item.office
            }
        )
        if not offices:
            return None
        office = generator.choice(offices)
        return Plant(
            replace(item, office=office),
            f"replaced the office {_get_shown_text(item.office)} with {office}",
        )
    if item.start_date is None:
        return None
    moved_start_date = _get_next_year(item.start_date)
    return Plant(
        replace(item, start_date=moved_start_date),
        f"moved the start date from {item.start_date} to {moved_start_date}",
    )


def draw_group(seed: int, group: str, group_items: list[CheckItem]) -> GroupDraw:
    generator = random.Random(f"{seed}:{group}")
    sorted_items = sorted(group_items, key=lambda item: item.row_id)
    if group == YEAR_ORDER_BREAK_GROUP:
        return GroupDraw(group, len(sorted_items), sorted_items, [], 0)
    sample = (
        sorted_items
        if len(sorted_items) <= _SAMPLE_SIZE
        else sorted(
            generator.sample(sorted_items, _SAMPLE_SIZE), key=lambda item: item.row_id
        )
    )
    sample_row_ids = {item.row_id for item in sample}
    items_outside_sample = [
        item for item in sorted_items if item.row_id not in sample_row_ids
    ]
    plant_candidates = items_outside_sample if items_outside_sample else sample
    plant_bases = sorted(
        generator.sample(
            plant_candidates, min(get_plant_count(len(sample)), len(plant_candidates))
        ),
        key=lambda item: item.row_id,
    )
    plants = []
    skipped_plant_count = 0
    for plant_base in plant_bases:
        plant = _get_plant(plant_base, group, sorted_items, generator)
        if plant is None:
            skipped_plant_count += 1
            continue
        plants.append(plant)
    return GroupDraw(group, len(sorted_items), sample, plants, skipped_plant_count)


def get_packet_entries(seed: int, group_draws: list[GroupDraw]) -> list[PacketEntry]:
    drawn_items: list[tuple[str, CheckItem, Optional[str]]] = [
        (group_draw.group, item, None)
        for group_draw in group_draws
        for item in group_draw.sample
    ]
    drawn_items.extend(
        (group_draw.group, plant.item, plant.note)
        for group_draw in group_draws
        for plant in group_draw.plants
    )
    random.Random(f"{seed}:packets").shuffle(drawn_items)
    return [
        PacketEntry(
            LeaveSeatCheckPacket(
                packet_id=f"packet-{index:05d}",
                source_text=item.source_text,
                data_says=_get_data_says(item),
                rule=_get_rule_text(group),
            ),
            LeaveSeatCheckKeyEntry(
                packet_id=f"packet-{index:05d}",
                group=group,
                table_name=item.table_name,
                row_id=item.row_id,
                is_plant=plant_note is not None,
                plant_note=plant_note,
            ),
        )
        for index, (group, item, plant_note) in enumerate(drawn_items, start=1)
    ]


def _get_draw_tsv_lines(group_draws: list[GroupDraw]) -> list[str]:
    draw_tsv_lines = [_DRAW_TSV_HEADER]
    for group_draw in group_draws:
        for item in group_draw.sample:
            draw_tsv_lines.append(
                f"{group_draw.group}\t{item.table_name}\t{item.row_id}\tFalse"
            )
        for plant in group_draw.plants:
            draw_tsv_lines.append(
                f"{group_draw.group}\t{plant.item.table_name}\t{plant.item.row_id}\tTrue"
            )
    return draw_tsv_lines


def _get_summary_lines(
    group_draws: list[GroupDraw], database_label: str, seed: int, read_at: datetime
) -> list[str]:
    return [
        f"database_label: {database_label}",
        f"seed: {seed}",
        f"read_at: {read_at.isoformat()}",
        "group\tframe\tsample\tplants\tskipped_plants",
        *(
            f"{group_draw.group}\t{group_draw.frame_count}\t{len(group_draw.sample)}"
            f"\t{len(group_draw.plants)}\t{group_draw.skipped_plant_count}"
            for group_draw in group_draws
        ),
        "",
    ]


def _write_draw_files(
    output_directory: Path,
    packet_entries: list[PacketEntry],
    draw_tsv_text: str,
    summary_text: str,
) -> str:
    with (output_directory / _PACKETS_FILE_NAME).open(
        "x", encoding="utf-8"
    ) as packets_file:
        for packet_entry in packet_entries:
            packets_file.write(packet_entry.packet.model_dump_json() + "\n")
    key_bytes = _KEY_ADAPTER.dump_json(
        [packet_entry.key_entry for packet_entry in packet_entries], indent=2
    )
    digest = hashlib.sha256(key_bytes).hexdigest()
    with (output_directory / _KEY_FILE_NAME).open("xb") as key_file:
        key_file.write(key_bytes)
    with (output_directory / _KEY_HASH_FILE_NAME).open(
        "x", encoding="utf-8"
    ) as key_hash_file:
        key_hash_file.write(f"{digest}\n")
    with (output_directory / _DRAW_TSV_FILE_NAME).open(
        "x", encoding="utf-8"
    ) as draw_tsv_file:
        draw_tsv_file.write(draw_tsv_text)
    with (output_directory / _SUMMARY_FILE_NAME).open(
        "x", encoding="utf-8"
    ) as summary_file:
        summary_file.write(summary_text)
    return digest


def build_leave_seat_check_packets(seed: int, output_directory: Path) -> None:
    database_label = get_database_label(settings.database_url)
    _validate_can_draw_from(database_label)
    try:
        output_directory.mkdir(parents=True)
    except FileExistsError as error:
        raise HansardHandCheckError(
            f"Refusing to write: {output_directory} already exists"
        ) from error
    logger.info(f"Drawing the leave and seat samples, read only, from {database_label}")
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_DRAW_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        read_at = datetime.now(timezone.utc)
        leave_check_rows = CRUDLeavePeriodPrinting(session).get_check_rows()
        seat_check_rows = CRUDSeatHolding(session).get_check_rows()
    group_to_items = get_group_to_items(leave_check_rows, seat_check_rows)
    group_draws = [
        draw_group(seed, group, group_to_items[group])
        for group in sorted(group_to_items)
    ]
    summary_lines = _get_summary_lines(group_draws, database_label, seed, read_at)
    digest = _write_draw_files(
        output_directory,
        get_packet_entries(seed, group_draws),
        "\n".join(_get_draw_tsv_lines(group_draws)) + "\n",
        "\n".join(summary_lines),
    )
    for line in summary_lines:
        logger.info(line)
    logger.info(f"Key SHA-256 {digest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Draw the leave and seat accuracy samples with sealed planted errors, read only"
    )
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="may not exist yet",
    )
    arguments = parser.parse_args()
    build_leave_seat_check_packets(arguments.seed, arguments.output_directory)
