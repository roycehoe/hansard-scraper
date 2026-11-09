import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.draw_office_check_sample as draw_script
from database.attendance import Attendance
from database.attendance_office import AttendanceOffice
from database.ministry import Ministry
from database.office_title_ministry import OfficeTitleMinistry
from database.report import Report
from database.report_participant import ReportParticipant
from database.report_put_to import ReportPutTo
from database.sitting import Sitting
from database.speech import Speech
from enums import (
    AttendanceOfficeSource,
    OfficeCheckRule,
    OfficeCheckVerdictKind,
    OfficeClass,
    OfficeTitleMinistrySource,
    ParticipantRole,
    ParticipantRoleSource,
    ReportPutToSource,
    ReportType,
    ReportVersion,
    SpeechKind,
)
from exceptions import HansardOfficeCheckError
from schemas.office_check import (
    OfficeCheckFlags,
    OfficeCheckPacket,
    OfficeCheckPackets,
    OfficeCheckPlantKey,
    OfficeCheckVerdict,
)
from scripts.draw_office_check_sample import (
    OfficeCheckDraw,
    OfficeCheckRow,
    OfficeCheckRuleRows,
    draw_office_check,
    draw_office_check_sample,
)
from scripts.list_office_check_flags import list_office_check_flags

_SEED = 20_261_112
_OTHER_SEED = 20_261_113
_ROUND_NUMBER = 1
_LARGE_GROUP = "1990 markdown"
_SMALL_GROUP = "1990 list"
_LARGE_GROUP_ROW_COUNT = 70
_SMALL_GROUP_ROW_COUNT = 3
_PLANT_VALUES = ["Defence", "Finance", "Health", "Law"]
_HEALTH_TITLE = "Minister for Health"
_DEFENCE_TITLE = "Minister for Defence"
_FINANCE_TITLE = "Minister for Finance"
_TABLE_KEY_PREFIXES = ("attendance_office:", "report_put_to:", "office_title_ministry:")
_PACKET_COUNT = 6
_DRAWN_PACKET_COUNT = 2
_PLANTED_PACKET_IDS = ("p4", "p5")
_RIGHT_PACKET_IDS = ("p0", "p1", "p2", "p3")
_PLANTED_VERDICT_NOTE = "checked against the line"


def _build_rows() -> list[OfficeCheckRow]:
    large_rows = [
        OfficeCheckRow(
            row_id,
            f"attendance_office:{row_id}",
            _LARGE_GROUP,
            f"line {row_id}",
            _PLANT_VALUES[row_id % len(_PLANT_VALUES)],
            "AFTER_NAME_COMMA",
        )
        for row_id in range(1, _LARGE_GROUP_ROW_COUNT + 1)
    ]
    small_rows = [
        OfficeCheckRow(
            _LARGE_GROUP_ROW_COUNT + row_id,
            f"attendance_office:{_LARGE_GROUP_ROW_COUNT + row_id}",
            _SMALL_GROUP,
            f"small line {row_id}",
            _PLANT_VALUES[row_id % len(_PLANT_VALUES)],
            "CHAIR_FORM",
        )
        for row_id in range(1, _SMALL_GROUP_ROW_COUNT + 1)
    ]
    return large_rows + small_rows


def _draw(seed: int) -> OfficeCheckDraw:
    return draw_office_check(
        OfficeCheckRule.ATTENDANCE_OFFICE,
        OfficeCheckRuleRows(_build_rows(), _PLANT_VALUES),
        seed,
    )


def test_a_draw_is_the_same_for_one_seed_and_different_for_another() -> None:
    assert _draw(_SEED) == _draw(_SEED)
    assert _draw(_SEED).packets != _draw(_OTHER_SEED).packets


def test_a_group_smaller_than_the_sample_is_sampled_whole() -> None:
    draw = _draw(_SEED)

    assert draw.group_to_sample_count[_SMALL_GROUP] == _SMALL_GROUP_ROW_COUNT
    assert draw.group_to_sample_count[_LARGE_GROUP] == draw_script._SAMPLE_PER_GROUP


def test_plants_come_from_outside_the_sample_with_another_rows_value() -> None:
    draw = _draw(_SEED)
    row_key_to_data_says = {office_check_row.row_key: office_check_row.data_says for office_check_row in _build_rows()}

    planted_packets = [
        packet for packet in draw.packets if packet.packet_id in draw.planted_packet_ids
    ]
    sampled_packets = [
        packet
        for packet in draw.packets
        if packet.packet_id not in draw.planted_packet_ids
    ]

    assert len(planted_packets) == draw_script._PLANTS_PER_ROUND
    assert {packet.row_key for packet in planted_packets}.isdisjoint(
        {packet.row_key for packet in sampled_packets}
    )
    assert all(
        packet.data_says != row_key_to_data_says[packet.row_key]
        for packet in planted_packets
    )
    assert all(
        packet.data_says == row_key_to_data_says[packet.row_key]
        for packet in sampled_packets
    )


def _seed_report(session: Session, sprs_report_id: str, office_printed: str) -> Report:
    report = Report(
        volumeNo=9,
        parlNo=9,
        sittingNo=None,
        sittingDate=datetime(2003, 3, 5),
        sno=1,
        original_title=sprs_report_id,
        title=sprs_report_id,
        reportId=sprs_report_id,
        reportType=ReportType.ORAL_ANSWER,
        content=None,
        markdown_content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS2,
    )
    session.add(report)
    session.flush()
    assert report.id is not None
    session.add_all(
        [
            Speech(
                ordinal=1,
                speaker=None,
                transcript=f"asked the {office_printed}",
                kind=SpeechKind.SPEECH,
                speaker_id=None,
                sitting_date=report.sitting_date,
                report_type=report.report_type,
                report_id=report.id,
            ),
            ReportPutTo(
                ordinal=1,
                office_printed=office_printed,
                printed_text=f"asked the {office_printed}",
                source=ReportPutToSource.ASKED_THE,
                first_ordinal=1,
                sprs_report_id=sprs_report_id,
            ),
        ]
    )
    return report


def _seed_office_rows(session: Session) -> None:
    sitting = Sitting(
        sitting_date="5-3-2003", parlement_no=9, markdown_content="PRESENT:"
    )
    health = Ministry(name="Health")
    defence = Ministry(name="Defence")
    finance = Ministry(name="Finance")
    session.add_all([sitting, health, defence, finance])
    session.flush()
    assert sitting.id is not None
    assert health.id is not None
    assert defence.id is not None
    assert finance.id is not None
    attendances = [
        Attendance(sitting_id=sitting.id, speaker_name=name, is_present=True)
        for name in ("Member One", "Member Two")
    ]
    session.add_all(attendances)
    session.flush()
    session.add_all(
        [
            AttendanceOffice(
                office_printed=office_printed,
                entry_line_printed=f"Member entry {index}, {office_printed}.",
                office_class=OfficeClass.MINISTER,
                source=AttendanceOfficeSource.AFTER_NAME_COMMA,
                extracted_at=datetime.now(timezone.utc),
                attendance_id=attendance.id,
            )
            for index, (attendance, office_printed) in enumerate(
                zip(attendances, (_HEALTH_TITLE, _DEFENCE_TITLE))
            )
            if attendance.id is not None
        ]
    )
    first_report = _seed_report(session, "report-one", _HEALTH_TITLE)
    _seed_report(session, "report-two", _DEFENCE_TITLE)
    assert first_report.id is not None
    session.add(
        ReportParticipant(
            ordinal=1,
            role=ParticipantRole.ANSWERER,
            role_source=ParticipantRoleSource.OFFICE_LABEL,
            first_ordinal=1,
            printed_name="Member One",
            office_printed=_FINANCE_TITLE,
            report_id=first_report.id,
        )
    )
    session.add_all(
        [
            OfficeTitleMinistry(
                office_printed=_HEALTH_TITLE,
                ordinal=1,
                source=OfficeTitleMinistrySource.CLOSED_LIST_RULE,
                ministry_id=health.id,
            ),
            OfficeTitleMinistry(
                office_printed=_DEFENCE_TITLE,
                ordinal=1,
                source=OfficeTitleMinistrySource.CLOSED_LIST_RULE,
                ministry_id=defence.id,
            ),
            OfficeTitleMinistry(
                office_printed=_FINANCE_TITLE,
                ordinal=1,
                source=OfficeTitleMinistrySource.CLOSED_LIST_RULE,
                ministry_id=finance.id,
            ),
        ]
    )
    session.commit()


@pytest.mark.parametrize(
    "rule",
    [
        OfficeCheckRule.ATTENDANCE_OFFICE,
        OfficeCheckRule.PUT_TO,
        OfficeCheckRule.MINISTRY,
    ],
)
def test_the_script_writes_packets_a_key_and_a_hash_and_hides_the_row_keys(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rule: OfficeCheckRule,
) -> None:
    _seed_office_rows(scratch_session)
    monkeypatch.setattr(
        draw_script, "build_read_only_engine", lambda database_url: scratch_engine
    )
    monkeypatch.setattr(draw_script, "_SAMPLE_PER_GROUP", 1)
    monkeypatch.setattr(draw_script, "_PLANTS_PER_ROUND", 1)
    output_directory = tmp_path / "draw"

    draw_office_check_sample(rule, _ROUND_NUMBER, _SEED, output_directory)

    packets = OfficeCheckPackets.model_validate_json(
        (output_directory / "records.json").read_text()
    ).root
    key_bytes = (output_directory / "plant-key.json").read_bytes()
    plant_key = OfficeCheckPlantKey.model_validate_json(key_bytes)
    assert len(packets) == _DRAWN_PACKET_COUNT
    assert len(plant_key.planted_packet_ids) == 1
    assert plant_key.planted_packet_ids[0] in {packet.packet_id for packet in packets}
    assert (output_directory / "plant-key.sha256").read_text() == (
        f"{hashlib.sha256(key_bytes).hexdigest()}\n"
    )
    reader_text = (output_directory / "reader-packets.md").read_text()
    for table_key_prefix in _TABLE_KEY_PREFIXES:
        assert table_key_prefix not in reader_text
    for packet in packets:
        assert packet.packet_id in reader_text
        assert packet.made_by not in reader_text
    summary_text = (output_directory / "summary.txt").read_text()
    assert f"Rule: {rule}" in summary_text
    assert "Plants: 1" in summary_text
    assert "password" not in summary_text


def test_the_script_refuses_an_existing_output_directory(
    scratch_engine: Engine,
    scratch_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_office_rows(scratch_session)
    monkeypatch.setattr(
        draw_script, "build_read_only_engine", lambda database_url: scratch_engine
    )

    with pytest.raises(HansardOfficeCheckError, match="exists"):
        draw_office_check_sample(OfficeCheckRule.PUT_TO, _ROUND_NUMBER, _SEED, tmp_path)


def _build_packets() -> list[OfficeCheckPacket]:
    return [
        OfficeCheckPacket(
            packet_id=f"p{index}",
            rule=OfficeCheckRule.PUT_TO,
            group="2000 oral-answer",
            source_text=f"asked the Minister {index}",
            data_says=f"Minister {index}",
            made_by="ASKED_THE",
            row_key=f"report_put_to:{index}",
        )
        for index in range(_PACKET_COUNT)
    ]


def _write_verdicts(
    directory: Path, packet_id_to_verdict: dict[str, OfficeCheckVerdictKind]
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "verdicts.jsonl").write_text(
        "\n".join(
            OfficeCheckVerdict(
                packet_id=packet_id, verdict=verdict, note=_PLANTED_VERDICT_NOTE
            ).model_dump_json()
            for packet_id, verdict in packet_id_to_verdict.items()
        )
        + "\n"
    )
    return directory


def _all_right() -> dict[str, OfficeCheckVerdictKind]:
    return {f"p{index}": OfficeCheckVerdictKind.RIGHT for index in range(_PACKET_COUNT)}


class _Inputs:
    def __init__(self, tmp_path: Path) -> None:
        self.records_path = tmp_path / "records.json"
        self.records_path.write_text(
            OfficeCheckPackets(_build_packets()).model_dump_json()
        )
        key_bytes = (
            OfficeCheckPlantKey(
                rule=OfficeCheckRule.PUT_TO,
                round_number=_ROUND_NUMBER,
                seed=_SEED,
                planted_packet_ids=list(_PLANTED_PACKET_IDS),
            )
            .model_dump_json(indent=2)
            .encode("utf-8")
        )
        self.key_path = tmp_path / "plant-key.json"
        self.key_path.write_bytes(key_bytes)
        self.key_hash_path = tmp_path / "plant-key.sha256"
        self.key_hash_path.write_text(f"{hashlib.sha256(key_bytes).hexdigest()}\n")
        self.output_path = tmp_path / "flags.json"
        self.summary_path = tmp_path / "summary.txt"
        self.sonnet_directory = tmp_path / "sonnet"
        self.opus_directory = tmp_path / "opus"

    def list_flags(self) -> None:
        list_office_check_flags(
            self.records_path,
            self.sonnet_directory,
            self.opus_directory,
            self.key_path,
            self.key_hash_path,
            self.output_path,
            self.summary_path,
        )


def test_a_sampled_row_marked_wrong_by_one_reader_is_a_flag(tmp_path: Path) -> None:
    inputs = _Inputs(tmp_path)
    sonnet_verdicts = _all_right()
    sonnet_verdicts["p1"] = OfficeCheckVerdictKind.WRONG
    opus_verdicts = _all_right()
    opus_verdicts["p2"] = OfficeCheckVerdictKind.CANNOT_TELL
    _write_verdicts(inputs.sonnet_directory, sonnet_verdicts)
    _write_verdicts(inputs.opus_directory, opus_verdicts)

    inputs.list_flags()

    flags = OfficeCheckFlags.model_validate_json(inputs.output_path.read_text()).root
    assert [flag.packet_id for flag in flags] == ["p1", "p2"]
    assert flags[0].sonnet_verdict == OfficeCheckVerdictKind.WRONG
    assert flags[0].opus_verdict == OfficeCheckVerdictKind.RIGHT
    assert flags[0].row_key == "report_put_to:1"


def test_a_plant_is_scored_and_is_not_a_flag(tmp_path: Path) -> None:
    inputs = _Inputs(tmp_path)
    sonnet_verdicts = _all_right()
    sonnet_verdicts["p4"] = OfficeCheckVerdictKind.WRONG
    _write_verdicts(inputs.sonnet_directory, sonnet_verdicts)
    _write_verdicts(inputs.opus_directory, _all_right())

    inputs.list_flags()

    flags = OfficeCheckFlags.model_validate_json(inputs.output_path.read_text()).root
    assert flags == []
    summary_text = inputs.summary_path.read_text()
    assert "Sonnet caught 1 of 2 plants; missed ['p5']" in summary_text
    assert "Opus caught 0 of 2 plants; missed ['p4', 'p5']" in summary_text


def test_a_missing_verdict_refuses_and_writes_nothing(tmp_path: Path) -> None:
    inputs = _Inputs(tmp_path)
    opus_verdicts = _all_right()
    del opus_verdicts["p3"]
    _write_verdicts(inputs.sonnet_directory, _all_right())
    _write_verdicts(inputs.opus_directory, opus_verdicts)

    with pytest.raises(HansardOfficeCheckError, match="Opus has no verdict"):
        inputs.list_flags()

    assert not inputs.output_path.exists()
    assert not inputs.summary_path.exists()


def test_a_verdict_for_an_unknown_packet_refuses(tmp_path: Path) -> None:
    inputs = _Inputs(tmp_path)
    sonnet_verdicts = _all_right()
    sonnet_verdicts["p99"] = OfficeCheckVerdictKind.RIGHT
    _write_verdicts(inputs.sonnet_directory, sonnet_verdicts)
    _write_verdicts(inputs.opus_directory, _all_right())

    with pytest.raises(HansardOfficeCheckError, match="do not exist"):
        inputs.list_flags()


def test_two_verdicts_for_one_packet_refuse(tmp_path: Path) -> None:
    inputs = _Inputs(tmp_path)
    _write_verdicts(inputs.sonnet_directory, _all_right())
    _write_verdicts(inputs.opus_directory, _all_right())
    with (inputs.opus_directory / "verdicts.jsonl").open("a") as verdicts_file:
        verdicts_file.write(
            json.dumps({"packet_id": "p0", "verdict": "WRONG", "note": "again"}) + "\n"
        )

    with pytest.raises(HansardOfficeCheckError, match="more than one verdict"):
        inputs.list_flags()


def test_a_verdict_line_that_does_not_parse_refuses(tmp_path: Path) -> None:
    inputs = _Inputs(tmp_path)
    _write_verdicts(inputs.sonnet_directory, _all_right())
    _write_verdicts(inputs.opus_directory, _all_right())
    (inputs.opus_directory / "verdicts.jsonl").write_text('{"packet_id": "p0"}\n')

    with pytest.raises(HansardOfficeCheckError, match="not a valid verdict line"):
        inputs.list_flags()


def test_a_changed_key_refuses(tmp_path: Path) -> None:
    inputs = _Inputs(tmp_path)
    _write_verdicts(inputs.sonnet_directory, _all_right())
    _write_verdicts(inputs.opus_directory, _all_right())
    inputs.key_path.write_bytes(inputs.key_path.read_bytes() + b" ")

    with pytest.raises(HansardOfficeCheckError, match="hashes to"):
        inputs.list_flags()

    assert not inputs.output_path.exists()


def test_a_second_run_refuses_over_an_existing_output(tmp_path: Path) -> None:
    inputs = _Inputs(tmp_path)
    _write_verdicts(inputs.sonnet_directory, _all_right())
    _write_verdicts(inputs.opus_directory, _all_right())
    inputs.list_flags()
    flags_text = inputs.output_path.read_text()

    with pytest.raises(HansardOfficeCheckError, match="exists"):
        inputs.list_flags()

    assert inputs.output_path.read_text() == flags_text
