import argparse
import hashlib
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlmodel import Session

from crud.attendance_office import CRUDAttendanceOffice
from crud.ministry import CRUDMinistry
from crud.office_title_ministry import CRUDOfficeTitleMinistry
from crud.report_participant import CRUDReportParticipant
from crud.report_put_to import CRUDReportPutTo
from database.attendance_office import AttendanceOffice
from database.init import build_read_only_engine
from database.office_title_ministry import OfficeTitleMinistry
from database.report_put_to import ReportPutTo
from enums import OfficeCheckRule
from exceptions import HansardOfficeCheckError
from logs import logger
from schemas.office_check import (
    OfficeCheckPacket,
    OfficeCheckPackets,
    OfficeCheckPlantKey,
)
from settings import settings
from utils.database_label import get_database_label
from utils.sitting_dates import get_decade, parse_sitting_date

_SAMPLE_PER_GROUP = 50
_PLANTS_PER_ROUND = 15
_DRAW_ISOLATION_LEVEL = "REPEATABLE READ"
_RECORDS_FILE_NAME = "records.json"
_READER_PACKETS_FILE_NAME = "reader-packets.md"
_PLANT_KEY_FILE_NAME = "plant-key.json"
_PLANT_KEY_HASH_FILE_NAME = "plant-key.sha256"
_SUMMARY_FILE_NAME = "summary.txt"
_RANDOM_BITS = 128
_MARKDOWN_SOURCE_GROUP = "markdown"
_LIST_SOURCE_GROUP = "list"


@dataclass(frozen=True)
class OfficeCheckRow:
    row_id: int
    row_key: str
    group: str
    source_text: str
    data_says: str
    made_by: str


@dataclass(frozen=True)
class OfficeCheckRuleRows:
    rows: list[OfficeCheckRow]
    plant_values: list[str]


@dataclass(frozen=True)
class OfficeCheckDraw:
    packets: list[OfficeCheckPacket]
    planted_packet_ids: list[str]
    group_to_row_count: dict[str, int]
    group_to_sample_count: dict[str, int]


def _get_attendance_office_rule_rows(session: Session) -> OfficeCheckRuleRows:
    rows = [
        OfficeCheckRow(
            attendance_office_check_row.id,
            f"{AttendanceOffice.__tablename__}:{attendance_office_check_row.id}",
            f"{get_decade(parse_sitting_date(attendance_office_check_row.sitting_date))}"
            f" {_MARKDOWN_SOURCE_GROUP if attendance_office_check_row.is_markdown_source else _LIST_SOURCE_GROUP}",
            attendance_office_check_row.entry_line_printed,
            attendance_office_check_row.office_printed,
            attendance_office_check_row.source,
        )
        for attendance_office_check_row in CRUDAttendanceOffice(
            session
        ).get_check_rows()
    ]
    return OfficeCheckRuleRows(rows, sorted({office_check_row.data_says for office_check_row in rows}))


def _get_put_to_rule_rows(session: Session) -> OfficeCheckRuleRows:
    rows = [
        OfficeCheckRow(
            report_put_to_check_row.id,
            f"{ReportPutTo.__tablename__}:{report_put_to_check_row.id}",
            f"{get_decade(report_put_to_check_row.sitting_date)} {report_put_to_check_row.report_type}",
            report_put_to_check_row.transcript,
            report_put_to_check_row.office_printed,
            report_put_to_check_row.source,
        )
        for report_put_to_check_row in CRUDReportPutTo(session).get_check_rows()
    ]
    return OfficeCheckRuleRows(rows, sorted({office_check_row.data_says for office_check_row in rows}))


def _get_title_to_first_print(session: Session) -> dict[str, datetime]:
    title_to_first_print: dict[str, datetime] = {}
    title_and_dates = [
        (
            attendance_office_sitting_row.office_printed,
            parse_sitting_date(attendance_office_sitting_row.sitting_date),
        )
        for attendance_office_sitting_row in CRUDAttendanceOffice(
            session
        ).get_sitting_rows()
    ]
    title_and_dates.extend(
        (report_put_to_check_row.office_printed, report_put_to_check_row.sitting_date)
        for report_put_to_check_row in CRUDReportPutTo(session).get_check_rows()
    )
    title_and_dates.extend(
        (
            report_participant_office_date_row.office_printed,
            report_participant_office_date_row.sitting_date,
        )
        for report_participant_office_date_row in CRUDReportParticipant(
            session
        ).get_office_printed_sitting_date_rows()
    )
    for office_printed, sitting_date in title_and_dates:
        first_print = title_to_first_print.get(office_printed)
        if first_print is None or sitting_date < first_print:
            title_to_first_print[office_printed] = sitting_date
    return title_to_first_print


def _get_ministry_rule_rows(session: Session) -> OfficeCheckRuleRows:
    ministry_id_to_name = {
        ministry.id: ministry.name for ministry in CRUDMinistry(session).get_all()
    }
    title_to_first_print = _get_title_to_first_print(session)
    rows: list[OfficeCheckRow] = []
    for office_title_ministry_row in CRUDOfficeTitleMinistry(session).get_rows():
        first_print = title_to_first_print.get(office_title_ministry_row.office_printed)
        if first_print is None:
            raise HansardOfficeCheckError(
                f"Title {office_title_ministry_row.office_printed!r} has a ministry row but is printed in no attendance entry, put-to or participant row"
            )
        rows.append(
            OfficeCheckRow(
                office_title_ministry_row.id,
                f"{OfficeTitleMinistry.__tablename__}:{office_title_ministry_row.id}",
                f"{get_decade(first_print)} {office_title_ministry_row.source}",
                office_title_ministry_row.office_printed,
                ministry_id_to_name[office_title_ministry_row.ministry_id],
                office_title_ministry_row.source,
            )
        )
    return OfficeCheckRuleRows(rows, sorted(ministry_id_to_name.values()))


def _get_rule_rows(session: Session, rule: OfficeCheckRule) -> OfficeCheckRuleRows:
    if rule == OfficeCheckRule.ATTENDANCE_OFFICE:
        return _get_attendance_office_rule_rows(session)
    if rule == OfficeCheckRule.PUT_TO:
        return _get_put_to_rule_rows(session)
    return _get_ministry_rule_rows(session)


def _build_packet(
    generator: random.Random, rule: OfficeCheckRule, office_check_row: OfficeCheckRow, data_says: str
) -> OfficeCheckPacket:
    return OfficeCheckPacket(
        packet_id=uuid.UUID(int=generator.getrandbits(_RANDOM_BITS), version=4).hex,
        rule=rule,
        group=office_check_row.group,
        source_text=office_check_row.source_text,
        data_says=data_says,
        made_by=office_check_row.made_by,
        row_key=office_check_row.row_key,
    )


def draw_office_check(
    rule: OfficeCheckRule, rule_rows: OfficeCheckRuleRows, seed: int
) -> OfficeCheckDraw:
    generator = random.Random(seed)
    sorted_rows = sorted(rule_rows.rows, key=lambda office_check_row: office_check_row.row_id)
    group_to_rows: defaultdict[str, list[OfficeCheckRow]] = defaultdict(list)
    for office_check_row in sorted_rows:
        group_to_rows[office_check_row.group].append(office_check_row)
    sampled_rows: list[OfficeCheckRow] = []
    group_to_sample_count: dict[str, int] = {}
    for group in sorted(group_to_rows):
        group_sample = generator.sample(
            group_to_rows[group], min(_SAMPLE_PER_GROUP, len(group_to_rows[group]))
        )
        sampled_rows.extend(group_sample)
        group_to_sample_count[group] = len(group_sample)
    sampled_row_ids = {office_check_row.row_id for office_check_row in sampled_rows}
    plantable_rows = [
        office_check_row
        for office_check_row in sorted_rows
        if office_check_row.row_id not in sampled_row_ids
        and any(value != office_check_row.data_says for value in rule_rows.plant_values)
    ]
    planted_rows = generator.sample(
        plantable_rows, min(_PLANTS_PER_ROUND, len(plantable_rows))
    )
    packets = [
        _build_packet(generator, rule, sampled_row, sampled_row.data_says)
        for sampled_row in sampled_rows
    ]
    planted_packets: list[OfficeCheckPacket] = []
    for planted_row in planted_rows:
        other_values = [
            value for value in rule_rows.plant_values if value != planted_row.data_says
        ]
        planted_packets.append(
            _build_packet(
                generator,
                rule,
                planted_row,
                other_values[generator.randrange(len(other_values))],
            )
        )
    packets.extend(planted_packets)
    generator.shuffle(packets)
    return OfficeCheckDraw(
        packets,
        sorted(planted_packet.packet_id for planted_packet in planted_packets),
        {group: len(group_rows) for group, group_rows in group_to_rows.items()},
        group_to_sample_count,
    )


def _get_reader_packets_text(packets: list[OfficeCheckPacket]) -> str:
    blocks = ["# Office check packets"]
    for packet in packets:
        quoted_source_text = "\n".join(
            f"> {line}" for line in packet.source_text.splitlines() or [""]
        )
        blocks.append(
            f"## Packet {packet.packet_id}\n\nSource text:\n\n{quoted_source_text}\n\nThe data says: {packet.data_says}"
        )
    return "\n\n".join(blocks) + "\n"


def _get_summary_text(
    rule: OfficeCheckRule, round_number: int, seed: int, draw: OfficeCheckDraw
) -> str:
    lines = [
        f"Rule: {rule}",
        f"Round: {round_number}",
        f"Seed: {seed}",
        f"Database: {get_database_label(settings.database_url)}",
    ]
    for group in sorted(draw.group_to_row_count):
        lines.append(
            f"Group {group}: {draw.group_to_row_count[group]} rows, {draw.group_to_sample_count[group]} sampled"
        )
    lines.append(f"Sampled: {sum(draw.group_to_sample_count.values())}")
    lines.append(f"Plants: {len(draw.planted_packet_ids)}")
    return "\n".join(lines) + "\n"


def draw_office_check_sample(
    rule: OfficeCheckRule, round_number: int, seed: int, output_directory: Path
) -> None:
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_DRAW_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        rule_rows = _get_rule_rows(session, rule)
    draw = draw_office_check(rule, rule_rows, seed)
    try:
        output_directory.mkdir(parents=True)
    except FileExistsError as error:
        raise HansardOfficeCheckError(
            f"{output_directory} exists; pass a directory that does not"
        ) from error
    (output_directory / _RECORDS_FILE_NAME).write_text(
        OfficeCheckPackets(draw.packets).model_dump_json(indent=1), encoding="utf-8"
    )
    (output_directory / _READER_PACKETS_FILE_NAME).write_text(
        _get_reader_packets_text(draw.packets), encoding="utf-8"
    )
    plant_key_bytes = (
        OfficeCheckPlantKey(
            rule=rule,
            round_number=round_number,
            seed=seed,
            planted_packet_ids=draw.planted_packet_ids,
        )
        .model_dump_json(indent=2)
        .encode("utf-8")
    )
    (output_directory / _PLANT_KEY_FILE_NAME).write_bytes(plant_key_bytes)
    (output_directory / _PLANT_KEY_HASH_FILE_NAME).write_text(
        f"{hashlib.sha256(plant_key_bytes).hexdigest()}\n", encoding="utf-8"
    )
    summary_text = _get_summary_text(rule, round_number, seed, draw)
    (output_directory / _SUMMARY_FILE_NAME).write_text(summary_text, encoding="utf-8")
    logger.info(
        f"Drew {len(draw.packets)} packets with {len(draw.planted_packet_ids)} plants into {output_directory}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Draw a seeded sample of stored office rows, with planted errors, for a reader check; read only"
    )
    parser.add_argument(
        "--rule",
        type=OfficeCheckRule,
        choices=list(OfficeCheckRule),
        required=True,
        help="the rule whose rows are drawn",
    )
    parser.add_argument(
        "--round",
        type=int,
        required=True,
        help="the round number, kept in the plant key",
    )
    parser.add_argument(
        "--seed", type=int, required=True, help="the seed of the draw and the plants"
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="a directory that does not exist yet",
    )
    arguments = parser.parse_args()
    draw_office_check_sample(
        arguments.rule, arguments.round, arguments.seed, arguments.output_directory
    )
