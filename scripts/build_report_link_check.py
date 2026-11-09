import argparse
import hashlib
import random
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from itertools import zip_longest
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.report import CRUDReport, ReportLinkReportRow
from crud.report_link import CRUDReportLink
from crud.speech import CRUDSpeech, SpeechRow
from database.init import build_read_only_engine
from enums import (
    ReportLinkPlantKind,
    ReportLinkRule,
    ReportLinkType,
    ReportVersion,
)
from exceptions import HansardReportLinkCheckError
from logs import logger
from populate.report_links import get_report_link_plan
from schemas.report_link_check import (
    ReportLinkCheckKey,
    ReportLinkCheckPacket,
    ReportLinkCheckPackets,
    ReportLinkCheckPlant,
    ReportLinkCheckReportText,
    ReportLinkCheckSameTitleReport,
)
from services.report_link import PlannedReportLink, ReportLinkPlan, get_part_number
from settings import settings
from utils.title_key import get_title_key

_SAMPLE_PER_GROUP = 50
_PLANTS_PER_GROUP = 5
_PLANTS_PER_RULE = 5
_OPENING_TEXT_LENGTH = 1_500
_CLOSING_TEXT_LENGTH = 500
_MAX_BATCH_PACKETS = 50
_MAX_BATCH_CHARACTERS = 80_000
_REPORT_BATCH = 200
_YEARS_PER_DECADE = 10
_PACKET_ID_BITS = 64
_MIN_SAME_TITLE_REPORTS = 2
_CORRECTION_GROUP = "correction"
_REPLY_GROUP = "reply"
_ONE_TITLE_GROUP = "continuation-one-title"
_LAST_PART_NEWER_GROUP = "last-part-newer-system"
_LAST_PART_OLDER_GROUP = "last-part-older-system"
_STAGE_ONE_GROUPS = (
    _CORRECTION_GROUP,
    _REPLY_GROUP,
    _ONE_TITLE_GROUP,
    _LAST_PART_NEWER_GROUP,
    _LAST_PART_OLDER_GROUP,
)
_READER_NAMES = ("sonnet", "opus")
_LOOSER_RULES = (
    ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE,
    ReportLinkRule.HAND_KEPT_TITLE_ON_PRINTED_DATE,
)


@dataclass(frozen=True)
class _ReportLookups:
    report_id_to_row: dict[str, ReportLinkReportRow]
    day_to_rows: dict[date, list[ReportLinkReportRow]]
    title_to_rows: dict[str, list[ReportLinkReportRow]]
    source_report_id_to_target_report_ids: dict[str, set[str]]


@dataclass(frozen=True)
class _PoolEntry:
    group: str
    planned_link: PlannedReportLink


@dataclass(frozen=True)
class _PlantAttempt:
    pool_entry: _PoolEntry
    plant_kind: ReportLinkPlantKind


@dataclass(frozen=True)
class _GroupDraw:
    group: str
    link_count: int
    sampled: list[PlannedReportLink]
    plant_pool: list[PlannedReportLink]


@dataclass(frozen=True)
class _Plant:
    group: str
    planned_link: PlannedReportLink
    plant_kind: ReportLinkPlantKind
    wrong_target: ReportLinkReportRow


@dataclass(frozen=True)
class _DrawnLink:
    group: str
    planned_link: PlannedReportLink
    plant_kind: Optional[ReportLinkPlantKind]
    target_row: ReportLinkReportRow
    same_title_rows: list[ReportLinkReportRow]


@dataclass(frozen=True)
class _PacketDraw:
    packet: ReportLinkCheckPacket
    drawn_link: _DrawnLink


@dataclass
class _Batch:
    markdowns: list[str]
    character_count: int
    citation_keys: set[tuple[str, str]]


def _validate_can_draw_check(session: Session, plan: ReportLinkPlan) -> None:
    stored_keys = {
        (
            report_link_row.source_report_id,
            report_link_row.target_report_id,
            report_link_row.link_type,
        )
        for report_link_row in CRUDReportLink(session).get_rows()
    }
    planned_keys = {
        (
            planned_link.source_report_id,
            planned_link.target_report_id,
            planned_link.link_type,
        )
        for planned_link in plan.planned_links
    }
    if stored_keys != planned_keys:
        raise HansardReportLinkCheckError(
            f"Stored report links differ from the plan: {len(stored_keys - planned_keys)} "
            f"stored only, {len(planned_keys - stored_keys)} planned only"
        )


def _build_lookups(
    report_rows: list[ReportLinkReportRow], plan: ReportLinkPlan
) -> _ReportLookups:
    day_to_rows: dict[date, list[ReportLinkReportRow]] = {}
    title_to_rows: dict[str, list[ReportLinkReportRow]] = {}
    for report_row in report_rows:
        day_to_rows.setdefault(report_row.sitting_date.date(), []).append(report_row)
        title_to_rows.setdefault(report_row.title, []).append(report_row)
    source_report_id_to_target_report_ids: dict[str, set[str]] = {}
    for planned_link in plan.planned_links:
        source_report_id_to_target_report_ids.setdefault(
            planned_link.source_report_id, set()
        ).add(planned_link.target_report_id)
    return _ReportLookups(
        {report_row.report_id: report_row for report_row in report_rows},
        day_to_rows,
        title_to_rows,
        source_report_id_to_target_report_ids,
    )


def _get_stage_one_group(
    planned_link: PlannedReportLink, target_row: ReportLinkReportRow
) -> Optional[str]:
    if planned_link.rule == ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE:
        if planned_link.link_type == ReportLinkType.CORRECTION:
            return _CORRECTION_GROUP
        if planned_link.link_type == ReportLinkType.REPLY:
            return _REPLY_GROUP
        return None
    if planned_link.rule == ReportLinkRule.SAME_TITLE_ON_PRINTED_DATE:
        return _ONE_TITLE_GROUP
    if planned_link.rule == ReportLinkRule.LAST_PART_ON_PRINTED_DATE:
        if target_row.report_version == ReportVersion.SPRS3:
            return _LAST_PART_NEWER_GROUP
        return _LAST_PART_OLDER_GROUP
    return None


def _get_stage_two_group(
    planned_link: PlannedReportLink, lookups: _ReportLookups
) -> str:
    source_row = lookups.report_id_to_row[planned_link.source_report_id]
    sitting_year = source_row.sitting_date.year
    decade = sitting_year // _YEARS_PER_DECADE * _YEARS_PER_DECADE
    return f"{decade}s {source_row.report_type}"


def _get_stage_one_group_to_links(
    plan: ReportLinkPlan, lookups: _ReportLookups
) -> dict[str, list[PlannedReportLink]]:
    group_to_links: dict[str, list[PlannedReportLink]] = {
        group: [] for group in _STAGE_ONE_GROUPS
    }
    for planned_link in plan.planned_links:
        group = _get_stage_one_group(
            planned_link, lookups.report_id_to_row[planned_link.target_report_id]
        )
        if group is not None:
            group_to_links[group].append(planned_link)
    return group_to_links


def _get_stage_two_group_to_links(
    plan: ReportLinkPlan, lookups: _ReportLookups, rule: ReportLinkRule
) -> dict[str, list[PlannedReportLink]]:
    group_to_links: dict[str, list[PlannedReportLink]] = {}
    for planned_link in plan.planned_links:
        if planned_link.rule != rule:
            continue
        group_to_links.setdefault(
            _get_stage_two_group(planned_link, lookups), []
        ).append(planned_link)
    return group_to_links


def _get_group_seed(seed: int, group: str) -> str:
    return f"{seed}:{group}"


def _get_group_draw(
    group: str, links: list[PlannedReportLink], generator: random.Random
) -> _GroupDraw:
    sampled = generator.sample(links, min(_SAMPLE_PER_GROUP, len(links)))
    sampled_links = set(sampled)
    unsampled = [link for link in links if link not in sampled_links]
    plant_pool = [
        *generator.sample(unsampled, len(unsampled)),
        *generator.sample(sampled, len(sampled)),
    ]
    return _GroupDraw(group, len(links), sampled, plant_pool)


def _get_plant_kinds(group: str) -> tuple[ReportLinkPlantKind, ...]:
    if group == _LAST_PART_NEWER_GROUP or group == _LAST_PART_OLDER_GROUP:
        return (ReportLinkPlantKind.EARLIER_PART,)
    return (
        ReportLinkPlantKind.OTHER_REPORT_SAME_DATE,
        ReportLinkPlantKind.SAME_TITLE_OTHER_DATE,
    )


def _get_wrong_target_candidates(
    true_target: ReportLinkReportRow,
    plant_kind: ReportLinkPlantKind,
    lookups: _ReportLookups,
) -> list[ReportLinkReportRow]:
    true_target_day = true_target.sitting_date.date()
    day_rows = lookups.day_to_rows[true_target_day]
    if plant_kind == ReportLinkPlantKind.OTHER_REPORT_SAME_DATE:
        return [
            report_row
            for report_row in day_rows
            if report_row.title != true_target.title
        ]
    if plant_kind == ReportLinkPlantKind.SAME_TITLE_OTHER_DATE:
        return [
            report_row
            for report_row in lookups.title_to_rows[true_target.title]
            if report_row.sitting_date.date() != true_target_day
        ]
    true_part_number = get_part_number(true_target)
    if true_part_number is None:
        return []
    earlier_rows: list[ReportLinkReportRow] = []
    for report_row in day_rows:
        part_number = get_part_number(report_row)
        if (
            report_row.title == true_target.title
            and part_number is not None
            and part_number < true_part_number
        ):
            earlier_rows.append(report_row)
    return earlier_rows


def _get_wrong_target(
    planned_link: PlannedReportLink,
    plant_kind: ReportLinkPlantKind,
    lookups: _ReportLookups,
    generator: random.Random,
) -> Optional[ReportLinkReportRow]:
    true_target = lookups.report_id_to_row[planned_link.target_report_id]
    excluded_report_ids = {
        planned_link.source_report_id,
        planned_link.target_report_id,
        *lookups.source_report_id_to_target_report_ids[planned_link.source_report_id],
    }
    candidates = sorted(
        (
            report_row
            for report_row in _get_wrong_target_candidates(
                true_target, plant_kind, lookups
            )
            if report_row.report_id not in excluded_report_ids
        ),
        key=lambda report_row: report_row.id,
    )
    if not candidates:
        return None
    return generator.choice(candidates)


def _walk_plant_pool(
    pool: list[_PoolEntry],
) -> Iterator[_PlantAttempt]:
    for position, pool_entry in enumerate(pool):
        plant_kinds = _get_plant_kinds(pool_entry.group)
        yield _PlantAttempt(pool_entry, plant_kinds[position % len(plant_kinds)])
    for pool_entry in pool:
        for plant_kind in _get_plant_kinds(pool_entry.group):
            yield _PlantAttempt(pool_entry, plant_kind)


def _draw_plants(
    pool: list[_PoolEntry],
    quota: int,
    scope: str,
    lookups: _ReportLookups,
    group_to_generator: dict[str, random.Random],
) -> list[_Plant]:
    plants: list[_Plant] = []
    tried_pairs: set[tuple[PlannedReportLink, ReportLinkPlantKind]] = set()
    for plant_attempt in _walk_plant_pool(pool):
        pool_entry = plant_attempt.pool_entry
        plant_kind = plant_attempt.plant_kind
        if (pool_entry.planned_link, plant_kind) in tried_pairs:
            continue
        tried_pairs.add((pool_entry.planned_link, plant_kind))
        wrong_target = _get_wrong_target(
            pool_entry.planned_link,
            plant_kind,
            lookups,
            group_to_generator[pool_entry.group],
        )
        if wrong_target is None:
            continue
        plants.append(
            _Plant(pool_entry.group, pool_entry.planned_link, plant_kind, wrong_target)
        )
        if len(plants) == quota:
            return plants
    raise HansardReportLinkCheckError(
        f"Drew {len(plants)} of {quota} plants for {scope}"
    )


def _get_same_title_rows(
    target_row: ReportLinkReportRow,
    link_type: ReportLinkType,
    lookups: _ReportLookups,
    generator: random.Random,
) -> list[ReportLinkReportRow]:
    if link_type != ReportLinkType.CONTINUATION:
        return []
    target_title_key = get_title_key(target_row.title)
    same_title_rows = [
        report_row
        for report_row in lookups.day_to_rows[target_row.sitting_date.date()]
        if get_title_key(report_row.title) == target_title_key
    ]
    if len(same_title_rows) < _MIN_SAME_TITLE_REPORTS:
        return []
    return generator.sample(same_title_rows, len(same_title_rows))


def _get_drawn_links(
    group_draws: list[_GroupDraw],
    plants: list[_Plant],
    lookups: _ReportLookups,
    group_to_generator: dict[str, random.Random],
) -> list[_DrawnLink]:
    drawn_links: list[_DrawnLink] = []
    for group_draw in group_draws:
        for planned_link in group_draw.sampled:
            target_row = lookups.report_id_to_row[planned_link.target_report_id]
            drawn_links.append(
                _DrawnLink(
                    group_draw.group,
                    planned_link,
                    None,
                    target_row,
                    _get_same_title_rows(
                        target_row,
                        planned_link.link_type,
                        lookups,
                        group_to_generator[group_draw.group],
                    ),
                )
            )
    for plant in plants:
        drawn_links.append(
            _DrawnLink(
                plant.group,
                plant.planned_link,
                plant.plant_kind,
                plant.wrong_target,
                _get_same_title_rows(
                    plant.wrong_target,
                    plant.planned_link.link_type,
                    lookups,
                    group_to_generator[plant.group],
                ),
            )
        )
    return drawn_links


def _get_report_texts(
    session: Session, drawn_links: list[_DrawnLink], lookups: _ReportLookups
) -> dict[int, str]:
    report_ids = sorted(
        {
            report_row.id
            for drawn_link in drawn_links
            for report_row in (
                lookups.report_id_to_row[drawn_link.planned_link.source_report_id],
                drawn_link.target_row,
                *drawn_link.same_title_rows,
            )
        }
    )
    report_id_to_speech_rows: dict[int, list[SpeechRow]] = {}
    for start in range(0, len(report_ids), _REPORT_BATCH):
        for speech_row in CRUDSpeech(session).get_rows_by_report_ids(
            report_ids[start : start + _REPORT_BATCH]
        ):
            report_id_to_speech_rows.setdefault(speech_row.report_id, []).append(
                speech_row
            )
    return {
        report_id: "\n\n".join(
            speech_row.transcript
            if speech_row.speaker is None
            else f"{speech_row.speaker}: {speech_row.transcript}"
            for speech_row in report_id_to_speech_rows.get(report_id, [])
        )
        for report_id in report_ids
    }


def _build_report_text(
    report_row: ReportLinkReportRow, report_id_to_text: dict[int, str]
) -> ReportLinkCheckReportText:
    return ReportLinkCheckReportText(
        title=report_row.title,
        sitting_date=report_row.sitting_date.date(),
        opening_text=report_id_to_text[report_row.id][:_OPENING_TEXT_LENGTH],
    )


def _build_packet_draws(
    drawn_links: list[_DrawnLink],
    lookups: _ReportLookups,
    report_id_to_text: dict[int, str],
    seed: int,
) -> list[_PacketDraw]:
    packet_id_generator = random.Random(f"{seed}:packet-ids")
    packet_draws: list[_PacketDraw] = []
    for drawn_link in drawn_links:
        planned_link = drawn_link.planned_link
        packet = ReportLinkCheckPacket(
            packet_id=f"{packet_id_generator.getrandbits(_PACKET_ID_BITS):016x}",
            group=drawn_link.group,
            rule=planned_link.rule,
            link_type=planned_link.link_type,
            source_report_id=planned_link.source_report_id,
            target_report_id=drawn_link.target_row.report_id,
            printed_citation=planned_link.printed_citation,
            paragraph=planned_link.paragraph,
            source_report=_build_report_text(
                lookups.report_id_to_row[planned_link.source_report_id],
                report_id_to_text,
            ),
            target_report=_build_report_text(drawn_link.target_row, report_id_to_text),
            same_title_reports=[
                ReportLinkCheckSameTitleReport(
                    title=same_title_row.title,
                    sitting_date=same_title_row.sitting_date.date(),
                    opening_text=report_id_to_text[same_title_row.id][
                        :_OPENING_TEXT_LENGTH
                    ],
                    closing_text=report_id_to_text[same_title_row.id][
                        -_CLOSING_TEXT_LENGTH:
                    ],
                    is_link_target=same_title_row.id == drawn_link.target_row.id,
                )
                for same_title_row in drawn_link.same_title_rows
            ],
        )
        packet_draws.append(_PacketDraw(packet, drawn_link))
    return packet_draws


def _get_packet_markdown(packet: ReportLinkCheckPacket) -> str:
    lines = [
        f"## Packet {packet.packet_id}",
        "",
        f"Link type: {packet.link_type}",
        f"Printed citation: {packet.printed_citation}",
        f"Paragraph: {packet.paragraph}",
        "",
        f"Citing report: {packet.source_report.title}, {packet.source_report.sitting_date}",
        "Opening text:",
        packet.source_report.opening_text,
        "",
        f"Linked report: {packet.target_report.title}, {packet.target_report.sitting_date}",
        "Opening text:",
        packet.target_report.opening_text,
    ]
    if packet.same_title_reports:
        lines.extend(["", "Reports with this title on that date:"])
        for same_title_report in packet.same_title_reports:
            marker = (
                " [this is the linked report]"
                if same_title_report.is_link_target
                else ""
            )
            lines.extend(
                [
                    "",
                    f"{same_title_report.title}, {same_title_report.sitting_date}{marker}",
                    "Opening text:",
                    same_title_report.opening_text,
                    "Closing text:",
                    same_title_report.closing_text,
                ]
            )
    return "\n".join(lines)


def _is_packet_allowed_in_batch(
    batch: _Batch, markdown: str, citation_key: tuple[str, str]
) -> bool:
    return (
        len(batch.markdowns) < _MAX_BATCH_PACKETS
        and batch.character_count + len(markdown) <= _MAX_BATCH_CHARACTERS
        and citation_key not in batch.citation_keys
    )


def _claim_batch_for_packet(
    batches: list[_Batch], markdown: str, citation_key: tuple[str, str]
) -> _Batch:
    for batch in batches:
        if _is_packet_allowed_in_batch(batch, markdown, citation_key):
            return batch
    new_batch = _Batch([], 0, set())
    batches.append(new_batch)
    return new_batch


def _get_batches(
    packets: list[ReportLinkCheckPacket], seed: int, reader_name: str
) -> list[_Batch]:
    generator = random.Random(f"{seed}:{reader_name}")
    batches: list[_Batch] = []
    for packet in generator.sample(packets, len(packets)):
        markdown = _get_packet_markdown(packet)
        citation_key = (packet.source_report_id, packet.printed_citation)
        batch = _claim_batch_for_packet(batches, markdown, citation_key)
        batch.markdowns.append(markdown)
        batch.character_count += len(markdown)
        batch.citation_keys.add(citation_key)
    return batches


def _get_draw_summary(
    seed: int,
    rule: Optional[ReportLinkRule],
    group_draws: list[_GroupDraw],
    plants: list[_Plant],
) -> str:
    group_to_plant_count = Counter(plant.group for plant in plants)
    lines = [f"seed: {seed}", f"stage: {'1' if rule is None else f'2 {rule}'}"]
    lines.extend(
        f"{group_draw.group}\t{_get_group_seed(seed, group_draw.group)}\t"
        f"links {group_draw.link_count}\tsampled {len(group_draw.sampled)}\t"
        f"plants {group_to_plant_count[group_draw.group]}"
        for group_draw in group_draws
    )
    return "\n".join(lines) + "\n"


def _write_check_files(
    output_directory: Path,
    packets: list[ReportLinkCheckPacket],
    key: ReportLinkCheckKey,
    draw_summary: str,
    seed: int,
) -> None:
    output_directory.mkdir(parents=True)
    records_directory = output_directory / "records"
    records_directory.mkdir()
    with (records_directory / "packets.json").open(
        "x", encoding="utf-8"
    ) as packets_file:
        packets_file.write(ReportLinkCheckPackets(packets).model_dump_json(indent=2))
    with (records_directory / "draw-summary.txt").open(
        "x", encoding="utf-8"
    ) as summary_file:
        summary_file.write(draw_summary)
    key_directory = output_directory / "key"
    key_directory.mkdir()
    key_bytes = key.model_dump_json(indent=2).encode("utf-8")
    with (key_directory / "plant-key.json").open("xb") as key_file:
        key_file.write(key_bytes)
    with (key_directory / "plant-key.sha256").open("x", encoding="utf-8") as hash_file:
        hash_file.write(f"{hashlib.sha256(key_bytes).hexdigest()}\n")
    for reader_name in _READER_NAMES:
        for batch_number, batch in enumerate(
            _get_batches(packets, seed, reader_name), start=1
        ):
            batch_directory = (
                output_directory / "batches" / reader_name / f"batch-{batch_number:02d}"
            )
            batch_directory.mkdir(parents=True)
            with (batch_directory / "packets.md").open(
                "x", encoding="utf-8"
            ) as batch_file:
                batch_file.write("\n\n".join(batch.markdowns) + "\n")


def _get_group_pool(group_draw: _GroupDraw) -> list[_PoolEntry]:
    return [
        _PoolEntry(group_draw.group, planned_link)
        for planned_link in group_draw.plant_pool
    ]


def _draw_stage_plants(
    group_draws: list[_GroupDraw],
    rule: Optional[ReportLinkRule],
    lookups: _ReportLookups,
    group_to_generator: dict[str, random.Random],
) -> list[_Plant]:
    if rule is None:
        return [
            plant
            for group_draw in group_draws
            for plant in _draw_plants(
                _get_group_pool(group_draw),
                _PLANTS_PER_GROUP,
                group_draw.group,
                lookups,
                group_to_generator,
            )
        ]
    round_robin_pool = [
        pool_entry
        for pool_entries in zip_longest(
            *(_get_group_pool(group_draw) for group_draw in group_draws)
        )
        for pool_entry in pool_entries
        if pool_entry is not None
    ]
    return _draw_plants(
        round_robin_pool, _PLANTS_PER_RULE, str(rule), lookups, group_to_generator
    )


def build_report_link_check(
    seed: int, output_directory: Path, rule: Optional[ReportLinkRule]
) -> None:
    with Session(build_read_only_engine(settings.database_url)) as session:
        plan = get_report_link_plan(session)
        _validate_can_draw_check(session, plan)
        lookups = _build_lookups(CRUDReport(session).get_link_report_rows(), plan)
        group_to_links = (
            _get_stage_one_group_to_links(plan, lookups)
            if rule is None
            else _get_stage_two_group_to_links(plan, lookups, rule)
        )
        group_to_generator = {
            group: random.Random(_get_group_seed(seed, group))
            for group in group_to_links
        }
        group_draws = [
            _get_group_draw(group, group_to_links[group], group_to_generator[group])
            for group in sorted(group_to_links)
        ]
        plants = _draw_stage_plants(group_draws, rule, lookups, group_to_generator)
        drawn_links = _get_drawn_links(group_draws, plants, lookups, group_to_generator)
        packet_draws = _build_packet_draws(
            drawn_links,
            lookups,
            _get_report_texts(session, drawn_links, lookups),
            seed,
        )
    packets = [packet_draw.packet for packet_draw in packet_draws]
    key = ReportLinkCheckKey(
        seed=seed,
        plants=[
            ReportLinkCheckPlant(
                packet_id=packet_draw.packet.packet_id,
                kind=packet_draw.drawn_link.plant_kind,
                true_target_report_id=packet_draw.drawn_link.planned_link.target_report_id,
            )
            for packet_draw in packet_draws
            if packet_draw.drawn_link.plant_kind is not None
        ],
    )
    _write_check_files(
        output_directory,
        packets,
        key,
        _get_draw_summary(seed, rule, group_draws, plants),
        seed,
    )
    for group_draw in group_draws:
        logger.info(
            f"{group_draw.group}: {group_draw.link_count:,} links, "
            f"{len(group_draw.sampled):,} sampled"
        )
    logger.info(f"Drew {len(packets):,} packets, {len(plants):,} planted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Draw the report link accuracy check: sampled links and planted errors, read only"
    )
    parser.add_argument("--seed", type=int, required=True, help="the draw's seed")
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="the check's directory; made by the script, so it may not exist yet",
    )
    parser.add_argument(
        "--rule",
        type=ReportLinkRule,
        choices=_LOOSER_RULES,
        help="draw the second stage for one looser rule; without it the first stage is drawn",
    )
    arguments = parser.parse_args()
    build_report_link_check(arguments.seed, arguments.output_directory, arguments.rule)
