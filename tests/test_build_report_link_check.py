import hashlib
import re
from collections import Counter
from datetime import datetime
from itertools import count
from pathlib import Path
from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.build_report_link_check as build_report_link_check_script
from database.report import Report
from database.report_link import ReportLink
from database.speech import Speech
from enums import (
    ReportLinkPlantKind,
    ReportLinkRule,
    ReportLinkType,
    ReportType,
    ReportVersion,
)
from exceptions import HansardReportLinkCheckError
from schemas.report_link_check import (
    ReportLinkCheckKey,
    ReportLinkCheckPacket,
    ReportLinkCheckPackets,
)
from scripts.build_report_link_check import build_report_link_check
from services.report_link import PlannedReportLink, ReportLinkPlan

_SEED = 7
_STAGE_ONE_GROUP_TO_LINK_COUNT = {
    "correction": 3,
    "reply": 3,
    "continuation-one-title": 3,
    "last-part-newer-system": 5,
    "last-part-older-system": 5,
}
_PLANTS_PER_GROUP = 5
_NEWER_GROUP = "last-part-newer-system"
_OLDER_GROUP = "last-part-older-system"
_PACKET_HEADING_RE = re.compile(r"^## Packet (\w+)$", re.MULTILINE)
_READER_NAMES = ("sonnet", "opus")
_LONG_TEXT_LENGTH = 2_000
_SAME_TITLE_PART_COUNT = 2
_STAGE_TWO_PLANT_COUNT = 5
_citation_numbers = count(1)


def _get_text(label: str) -> str:
    return f"{label} start " + "x" * _LONG_TEXT_LENGTH + f" {label} end"


def _get_reports(session: Session) -> list[Report]:
    return list(session.exec(select(Report)).all())


def _add_report(
    session: Session,
    report_id: str,
    report_type: ReportType,
    sitting_date: datetime,
    title: str,
    report_version: ReportVersion = ReportVersion.SPRS3,
    html_file_name: Optional[str] = None,
) -> Report:
    report = Report(
        volume_number=94,
        parliament_number=14,
        sitting_date=sitting_date,
        speech_number=1,
        original_title=title,
        title=title,
        report_id=report_id,
        report_type=report_type,
        content="Text.",
        report_version=report_version,
        html_file_name=html_file_name,
    )
    session.add(report)
    session.flush()
    assert report.id is not None
    session.add(
        Speech(
            ordinal=1,
            speaker=None,
            transcript=_get_text(f"label-{report.id}"),
            sitting_date=sitting_date,
            report_type=report_type,
            report_id=report.id,
        )
    )
    return report


def _add_target_with_decoys(
    session: Session,
    report_id: str,
    report_type: ReportType,
    sitting_date: datetime,
    title: str,
) -> None:
    _add_report(session, report_id, report_type, sitting_date, title)
    _add_report(
        session, f"{report_id}-decoy", report_type, sitting_date, f"{title} decoy"
    )
    _add_report(
        session,
        f"{report_id}-twin",
        report_type,
        sitting_date.replace(year=sitting_date.year - 1),
        title,
    )


def _build_link(
    link_type: ReportLinkType,
    rule: ReportLinkRule,
    source_report_id: str,
    target_report_id: str,
) -> PlannedReportLink:
    citation = f'"Printed title {next(_citation_numbers)}", Official Report'
    return PlannedReportLink(
        link_type,
        rule,
        citation,
        source_report_id,
        target_report_id,
        1,
        f"[Please refer to {citation}]",
    )


def _store_plan(session: Session, plan: ReportLinkPlan) -> None:
    session.flush()
    session.add_all(
        [
            ReportLink(
                link_type=planned_link.link_type,
                rule=planned_link.rule,
                printed_citation=planned_link.printed_citation,
                source_report_id=planned_link.source_report_id,
                target_report_id=planned_link.target_report_id,
            )
            for planned_link in plan.planned_links
        ]
    )
    session.commit()


def _seed_stage_one(session: Session) -> ReportLinkPlan:
    planned_links: list[PlannedReportLink] = []
    for number in range(1, 4):
        _add_target_with_decoys(
            session,
            f"CT{number}",
            ReportType.ORAL_ANSWER,
            datetime(2020, 3, number),
            f"Correction target {number}",
        )
        _add_report(
            session,
            f"CS{number}",
            ReportType.CLARIFICATION,
            datetime(2020, 5, number),
            f"Correction {number}",
        )
        planned_links.append(
            _build_link(
                ReportLinkType.CORRECTION,
                ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE,
                f"CS{number}",
                f"CT{number}",
            )
        )
        _add_target_with_decoys(
            session,
            f"RT{number}",
            ReportType.WRITTEN_ANSWER,
            datetime(2020, 3, number),
            f"Reply target {number}",
        )
        _add_report(
            session,
            f"RS{number}",
            ReportType.ORAL_ANSWER,
            datetime(2020, 5, number),
            f"Reply {number}",
        )
        planned_links.append(
            _build_link(
                ReportLinkType.REPLY,
                ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE,
                f"RS{number}",
                f"RT{number}",
            )
        )
        _add_target_with_decoys(
            session,
            f"OT{number}",
            ReportType.MOTION,
            datetime(2020, 3, number),
            f"One title debate {number}",
        )
        _add_report(
            session,
            f"OS{number}",
            ReportType.MOTION,
            datetime(2020, 5, number),
            f"One title debate {number}",
        )
        planned_links.append(
            _build_link(
                ReportLinkType.CONTINUATION,
                ReportLinkRule.SAME_TITLE_ON_PRINTED_DATE,
                f"OS{number}",
                f"OT{number}",
            )
        )
    for number in range(1, 6):
        for prefix, report_version, group_title in (
            ("LN", ReportVersion.SPRS3, "Newer debate"),
            ("LO", ReportVersion.SPRS2, "Older debate"),
        ):
            title = f"{group_title} {number}"
            for part in (1, 2):
                _add_report(
                    session,
                    f"{prefix}{number}-{part}",
                    ReportType.MOTION,
                    datetime(2020, 3, number),
                    title,
                    report_version,
                    f"{part}-{prefix}{number}",
                )
            _add_report(
                session,
                f"{prefix}S{number}",
                ReportType.MOTION,
                datetime(2020, 6, number),
                title,
                report_version,
                f"9-{prefix}S{number}",
            )
            planned_links.append(
                _build_link(
                    ReportLinkType.CONTINUATION,
                    ReportLinkRule.LAST_PART_ON_PRINTED_DATE,
                    f"{prefix}S{number}",
                    f"{prefix}{number}-2",
                )
            )
    plan = ReportLinkPlan(planned_links, [])
    _store_plan(session, plan)
    return plan


def _seed_stage_two(session: Session, link_count: int) -> ReportLinkPlan:
    source_types_and_years = (
        (ReportType.ORAL_ANSWER, 2015),
        (ReportType.WRITTEN_ANSWER, 2015),
        (ReportType.ORAL_ANSWER, 2022),
    )
    planned_links: list[PlannedReportLink] = []
    for number, (report_type, year) in enumerate(
        source_types_and_years[:link_count], start=1
    ):
        _add_target_with_decoys(
            session,
            f"KT{number}",
            ReportType.ORAL_ANSWER,
            datetime(year, 3, number),
            f"Key target {number}",
        )
        _add_report(
            session,
            f"KS{number}",
            report_type,
            datetime(year, 5, number),
            f"Key source {number}",
        )
        planned_links.append(
            _build_link(
                ReportLinkType.REPLY,
                ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE,
                f"KS{number}",
                f"KT{number}",
            )
        )
    plan = ReportLinkPlan(planned_links, [])
    _store_plan(session, plan)
    return plan


def _run_check(
    monkeypatch: pytest.MonkeyPatch,
    scratch_engine: Engine,
    plan: ReportLinkPlan,
    output_directory: Path,
    rule: Optional[ReportLinkRule] = None,
) -> None:
    monkeypatch.setattr(
        build_report_link_check_script,
        "build_read_only_engine",
        lambda database_url: scratch_engine,
    )
    monkeypatch.setattr(
        build_report_link_check_script,
        "get_report_link_plan",
        lambda session: plan,
    )
    build_report_link_check(_SEED, output_directory, rule)


def _read_packets(output_directory: Path) -> list[ReportLinkCheckPacket]:
    return ReportLinkCheckPackets.model_validate_json(
        (output_directory / "records" / "packets.json").read_text(encoding="utf-8")
    ).root


def _read_key(output_directory: Path) -> ReportLinkCheckKey:
    return ReportLinkCheckKey.model_validate_json(
        (output_directory / "key" / "plant-key.json").read_text(encoding="utf-8")
    )


def _get_batch_names(output_directory: Path, reader_name: str) -> dict[str, str]:
    packet_id_to_batch_name: dict[str, str] = {}
    for packets_path in sorted(
        (output_directory / "batches" / reader_name).glob("batch-*/packets.md")
    ):
        for packet_id in _PACKET_HEADING_RE.findall(
            packets_path.read_text(encoding="utf-8")
        ):
            packet_id_to_batch_name[packet_id] = packets_path.parent.name
    return packet_id_to_batch_name


def test_stage_one_builds_the_five_groups_and_reads_every_link(
    scratch_session: Session,
    scratch_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _seed_stage_one(scratch_session)
    output_directory = tmp_path / "check"

    _run_check(monkeypatch, scratch_engine, plan, output_directory)

    packets = _read_packets(output_directory)
    plant_packet_ids = {plant.packet_id for plant in _read_key(output_directory).plants}
    sampled_packets = [
        packet for packet in packets if packet.packet_id not in plant_packet_ids
    ]
    assert Counter(packet.group for packet in sampled_packets) == (
        _STAGE_ONE_GROUP_TO_LINK_COUNT
    )
    assert {
        (packet.source_report_id, packet.target_report_id) for packet in sampled_packets
    } == {
        (planned_link.source_report_id, planned_link.target_report_id)
        for planned_link in plan.planned_links
    }
    assert Counter(
        packet.group for packet in packets if packet.packet_id in plant_packet_ids
    ) == {group: _PLANTS_PER_GROUP for group in _STAGE_ONE_GROUP_TO_LINK_COUNT}


def test_a_groups_plants_match_its_kinds_and_point_at_the_wrong_report(
    scratch_session: Session,
    scratch_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _seed_stage_one(scratch_session)
    output_directory = tmp_path / "check"
    report_id_to_report = {
        report.report_id: report for report in _get_reports(scratch_session)
    }

    _run_check(monkeypatch, scratch_engine, plan, output_directory)

    packet_id_to_packet = {
        packet.packet_id: packet for packet in _read_packets(output_directory)
    }
    plants = _read_key(output_directory).plants
    assert len(plants) == _PLANTS_PER_GROUP * len(_STAGE_ONE_GROUP_TO_LINK_COUNT)
    for plant in plants:
        packet = packet_id_to_packet[plant.packet_id]
        true_target = report_id_to_report[plant.true_target_report_id]
        planted_target = report_id_to_report[packet.target_report_id]
        assert planted_target.report_id != true_target.report_id
        assert packet.target_report_id != packet.source_report_id
        if packet.group == _NEWER_GROUP or packet.group == _OLDER_GROUP:
            assert plant.kind == ReportLinkPlantKind.EARLIER_PART
            assert planted_target.sitting_date == true_target.sitting_date
            assert planted_target.title == true_target.title
        elif plant.kind == ReportLinkPlantKind.OTHER_REPORT_SAME_DATE:
            assert planted_target.sitting_date == true_target.sitting_date
            assert planted_target.title != true_target.title
        else:
            assert plant.kind == ReportLinkPlantKind.SAME_TITLE_OTHER_DATE
            assert planted_target.sitting_date != true_target.sitting_date
            assert planted_target.title == true_target.title


def test_a_plant_copying_a_sampled_link_lands_in_another_batch_for_each_reader(
    scratch_session: Session,
    scratch_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _seed_stage_one(scratch_session)
    output_directory = tmp_path / "check"

    _run_check(monkeypatch, scratch_engine, plan, output_directory)

    packets = _read_packets(output_directory)
    citation_to_packet_ids: dict[tuple[str, str], list[str]] = {}
    for packet in packets:
        citation_to_packet_ids.setdefault(
            (packet.source_report_id, packet.printed_citation), []
        ).append(packet.packet_id)
    assert any(len(packet_ids) > 1 for packet_ids in citation_to_packet_ids.values())
    for reader_name in _READER_NAMES:
        packet_id_to_batch_name = _get_batch_names(output_directory, reader_name)
        assert set(packet_id_to_batch_name) == {packet.packet_id for packet in packets}
        for packet_ids in citation_to_packet_ids.values():
            assert len(
                {packet_id_to_batch_name[packet_id] for packet_id in packet_ids}
            ) == (len(packet_ids))


def test_packets_markdown_holds_no_report_id_rule_or_group_name(
    scratch_session: Session,
    scratch_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _seed_stage_one(scratch_session)
    output_directory = tmp_path / "check"

    _run_check(monkeypatch, scratch_engine, plan, output_directory)

    markdown = "\n".join(
        packets_path.read_text(encoding="utf-8")
        for packets_path in (output_directory / "batches").glob("*/batch-*/packets.md")
    )
    assert markdown
    forbidden_texts = {
        *_STAGE_ONE_GROUP_TO_LINK_COUNT,
        *(rule.value for rule in ReportLinkRule),
        *(report.report_id for report in _get_reports(scratch_session)),
    }
    for forbidden_text in forbidden_texts:
        assert forbidden_text not in markdown


def test_a_continuation_with_several_same_title_reports_shows_each_and_marks_the_target(
    scratch_session: Session,
    scratch_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _seed_stage_one(scratch_session)
    output_directory = tmp_path / "check"

    _run_check(monkeypatch, scratch_engine, plan, output_directory)

    packets = _read_packets(output_directory)
    last_part_packets = [packet for packet in packets if packet.group == _NEWER_GROUP]
    assert last_part_packets
    markdown = "\n".join(
        packets_path.read_text(encoding="utf-8")
        for packets_path in (output_directory / "batches" / "opus").glob(
            "batch-*/packets.md"
        )
    )
    for packet in last_part_packets:
        assert len(packet.same_title_reports) == _SAME_TITLE_PART_COUNT
        assert [
            same_title_report.is_link_target
            for same_title_report in packet.same_title_reports
        ].count(True) == 1
        for same_title_report in packet.same_title_reports:
            assert same_title_report.opening_text in markdown
            assert same_title_report.closing_text in markdown
    assert "[this is the linked report]" in markdown
    single_title_packets = [
        packet
        for packet in packets
        if packet.group == "continuation-one-title"
        or packet.link_type != ReportLinkType.CONTINUATION
    ]
    assert all(not packet.same_title_reports for packet in single_title_packets)


def test_a_second_stage_rule_with_one_link_per_group_still_draws_five_plants(
    scratch_session: Session,
    scratch_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _seed_stage_two(scratch_session, 3)
    output_directory = tmp_path / "check"

    _run_check(
        monkeypatch,
        scratch_engine,
        plan,
        output_directory,
        ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE,
    )

    packets = _read_packets(output_directory)
    assert len(_read_key(output_directory).plants) == _STAGE_TWO_PLANT_COUNT
    assert len(packets) == 3 + _STAGE_TWO_PLANT_COUNT
    assert {packet.group for packet in packets} == {
        "2010s oral-answer",
        "2010s written-answer",
        "2020s oral-answer",
    }


def test_a_second_stage_rule_raises_when_its_links_and_kinds_run_out(
    scratch_session: Session,
    scratch_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _seed_stage_two(scratch_session, 2)
    output_directory = tmp_path / "check"

    with pytest.raises(HansardReportLinkCheckError, match="Drew 4 of 5 plants"):
        _run_check(
            monkeypatch,
            scratch_engine,
            plan,
            output_directory,
            ReportLinkRule.TITLE_KEY_ON_PRINTED_DATE,
        )

    assert not output_directory.exists()


def test_the_key_hash_matches_its_file(
    scratch_session: Session,
    scratch_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _seed_stage_one(scratch_session)
    output_directory = tmp_path / "check"

    _run_check(monkeypatch, scratch_engine, plan, output_directory)

    key_bytes = (output_directory / "key" / "plant-key.json").read_bytes()
    stored_hash = (output_directory / "key" / "plant-key.sha256").read_text(
        encoding="utf-8"
    )
    assert stored_hash.strip() == hashlib.sha256(key_bytes).hexdigest()


def test_an_existing_output_directory_raises(
    scratch_session: Session,
    scratch_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _seed_stage_one(scratch_session)

    with pytest.raises(FileExistsError):
        _run_check(monkeypatch, scratch_engine, plan, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_stored_rows_that_differ_from_the_plan_raise(
    scratch_session: Session,
    scratch_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _seed_stage_one(scratch_session)
    stored_link = scratch_session.exec(select(ReportLink)).first()
    assert stored_link is not None
    scratch_session.delete(stored_link)
    scratch_session.commit()
    output_directory = tmp_path / "check"

    with pytest.raises(
        HansardReportLinkCheckError,
        match="differ from the plan: 0 stored only, 1 planned only",
    ):
        _run_check(monkeypatch, scratch_engine, plan, output_directory)

    assert not output_directory.exists()
