from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.build_attached_file_check as build_attached_file_check_script
from database.attached_file import AttachedFile
from database.attached_file_pointer import AttachedFilePointer
from database.report import Report
from database.sitting import Sitting
from database.speech import Speech
from enums import (
    AttachedFileCheckPlantKind,
    AttachedFileKind,
    AttachedFilePointerShape,
    ParagraphTieRule,
    ReportType,
    ReportVersion,
    SpeechKind,
)
from exceptions import HansardAttachedFileError
from schemas.attached_file_check import (
    AttachedFileCheckKey,
    AttachedFileCheckPackets,
)
from scripts.build_attached_file_check import build_attached_file_check
from services.attached_file import get_pointer_paragraph_text

_ROUND_NUMBER = 1
_LINK_WORDS = "Annex A"
_DATED_FOLDER = "20230301"
_DOWNLOAD_PATH = "/search/search/download?value="
_REPORT_ID_PREFIX = "sprs-report-"
_FIRST_TRANSCRIPT = "See Annex A here."
_OTHER_TRANSCRIPT = "Nothing to see."
_SECOND_LINK_TRANSCRIPT = "Annex A again."
_SEEDED_REPORT_COUNT = 5
_CAPPED_SAMPLE_SIZE = 2
_SAMPLE_SIZE = 4
_PLANTS_PER_KIND = 3
_CUT_PARAGRAPH_LENGTH = 2_000
_PLANT_COUNT = 6
_SECOND_ORDINAL = 2
_THIRD_ORDINAL = 3


def _seed(
    session: Session,
    report_count: int,
    transcripts: list[str],
    file_kinds: list[AttachedFileKind],
) -> list[int]:
    pointer_ids = []
    for report_number in range(report_count):
        sitting = Sitting(parlement_no=14, sitting_date=f"{report_number + 1}-3-2023")
        session.add(sitting)
        session.flush()
        assert sitting.id is not None
        attached_files = [
            AttachedFile(
                kind=file_kind,
                sprs_file_id=file_number,
                printed_title=f"File {report_number}-{file_number}",
                printed_file_path=f"path-{report_number}-{file_number}",
                file_name=f"name-{report_number}-{file_number}",
                download_value=f"{_DATED_FOLDER}/annex-{report_number}-{file_number}.pdf",
                sitting_id=sitting.id,
            )
            for file_number, file_kind in enumerate(file_kinds, 1)
        ]
        session.add_all(attached_files)
        sprs_report_id = f"{_REPORT_ID_PREFIX}{report_number:04d}"
        download_value = f"{_DATED_FOLDER}/annex-{report_number}-1.pdf"
        href = f"{_DOWNLOAD_PATH}{download_value}"
        report = Report(
            volumeNo=14,
            parlNo=14,
            sittingNo=None,
            sittingDate=datetime(2023, 3, report_number + 1),
            sno=1,
            original_title="Sample",
            title=f"Sample {report_number}",
            reportId=sprs_report_id,
            reportType=ReportType.MOTION,
            content=f'<p>See <a href="{href}">{_LINK_WORDS}</a> here.</p>',
            htmlFileName=None,
            reportVersion=ReportVersion.SPRS3,
        )
        session.add(report)
        session.flush()
        assert report.id is not None
        session.add_all(
            Speech(
                ordinal=ordinal,
                speaker=None,
                transcript=transcript,
                kind=SpeechKind.SPEECH,
                speaker_id=None,
                sitting_date=report.sitting_date,
                report_type=report.report_type,
                report_id=report.id,
            )
            for ordinal, transcript in enumerate(transcripts, 1)
        )
        pointer = AttachedFilePointer(
            ordinal=1,
            printed_text=_LINK_WORDS,
            href=href,
            shape=AttachedFilePointerShape.DATED,
            download_value=download_value,
            speech_ordinal=1,
            paragraph_tie_rule=ParagraphTieRule.ONLY_OCCURRENCE,
            sprs_report_id=sprs_report_id,
            attached_file_id=attached_files[0].id if attached_files else None,
        )
        session.add(pointer)
        session.flush()
        assert pointer.id is not None
        pointer_ids.append(pointer.id)
    session.commit()
    return pointer_ids


@pytest.fixture
def read_only_scratch(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        build_attached_file_check_script,
        "build_read_only_engine",
        lambda database_url: scratch_engine,
    )


def _read_key(output_directory: Path) -> AttachedFileCheckKey:
    return AttachedFileCheckKey.model_validate_json(
        (output_directory / "records" / "key.json").read_text(encoding="utf-8")
    )


def _read_packets(output_directory: Path) -> AttachedFileCheckPackets:
    return AttachedFileCheckPackets.model_validate_json(
        (output_directory / "records" / "packets.json").read_text(encoding="utf-8")
    )


def _set_sizes(
    monkeypatch: pytest.MonkeyPatch, group_sample_size: int, plants_per_kind: int
) -> None:
    monkeypatch.setattr(
        build_attached_file_check_script, "_GROUP_SAMPLE_SIZE", group_sample_size
    )
    monkeypatch.setattr(
        build_attached_file_check_script, "_PLANTS_PER_KIND", plants_per_kind
    )


def test_a_fixed_seed_draws_the_same_rows_twice(
    scratch_session: Session,
    read_only_scratch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(
        scratch_session,
        12,
        [_FIRST_TRANSCRIPT, _OTHER_TRANSCRIPT],
        [AttachedFileKind.ANNEX, AttachedFileKind.ANNEX],
    )
    _set_sizes(monkeypatch, 4, 2)

    build_attached_file_check(_ROUND_NUMBER, tmp_path / "first")
    build_attached_file_check(_ROUND_NUMBER, tmp_path / "second")

    for file_name in ("packets.json", "key.json", "key.sha256"):
        assert (tmp_path / "first" / "records" / file_name).read_bytes() == (
            tmp_path / "second" / "records" / file_name
        ).read_bytes()


def test_a_group_below_the_sample_size_takes_all_and_a_larger_one_is_capped(
    scratch_session: Session,
    read_only_scratch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(
        scratch_session,
        _SEEDED_REPORT_COUNT,
        [_FIRST_TRANSCRIPT],
        [AttachedFileKind.ANNEX],
    )
    _set_sizes(monkeypatch, 50, 0)

    build_attached_file_check(_ROUND_NUMBER, tmp_path / "all")
    _set_sizes(monkeypatch, _CAPPED_SAMPLE_SIZE, 0)
    build_attached_file_check(_ROUND_NUMBER, tmp_path / "capped")

    assert len(_read_packets(tmp_path / "all").root) == _SEEDED_REPORT_COUNT
    assert len(_read_packets(tmp_path / "capped").root) == _CAPPED_SAMPLE_SIZE


def test_plants_are_outside_the_sample_and_no_pointer_has_two_plants(
    scratch_session: Session,
    read_only_scratch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(
        scratch_session,
        14,
        [_FIRST_TRANSCRIPT, _OTHER_TRANSCRIPT],
        [AttachedFileKind.ANNEX, AttachedFileKind.ANNEX],
    )
    _set_sizes(monkeypatch, _SAMPLE_SIZE, _PLANTS_PER_KIND)

    build_attached_file_check(_ROUND_NUMBER, tmp_path / "check")

    key = _read_key(tmp_path / "check")
    pointer_ids = list(key.packet_id_to_pointer_id.values())
    assert len(key.plants) == _PLANT_COUNT
    assert len(pointer_ids) == _SAMPLE_SIZE + _PLANT_COUNT
    assert len(set(pointer_ids)) == len(pointer_ids)
    kinds = [plant.kind for plant in key.plants]
    assert kinds.count(AttachedFileCheckPlantKind.PARAGRAPH) == _PLANTS_PER_KIND
    assert kinds.count(AttachedFileCheckPlantKind.FILE) == _PLANTS_PER_KIND


def test_a_file_plant_stays_within_kind_when_the_sitting_has_one(
    scratch_session: Session,
    read_only_scratch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(
        scratch_session,
        6,
        [_FIRST_TRANSCRIPT],
        [AttachedFileKind.ANNEX, AttachedFileKind.VERNACULAR, AttachedFileKind.ANNEX],
    )
    _set_sizes(monkeypatch, 1, 15)

    build_attached_file_check(_ROUND_NUMBER, tmp_path / "check")

    key = _read_key(tmp_path / "check")
    packet_id_to_packet = {
        packet.packet_id: packet for packet in _read_packets(tmp_path / "check").root
    }
    file_plants = [
        plant for plant in key.plants if plant.kind == AttachedFileCheckPlantKind.FILE
    ]
    assert file_plants
    for plant in file_plants:
        packet = packet_id_to_packet[plant.packet_id]
        assert packet.attached_file_id != plant.true_attached_file_id
        assert packet.file_kind == AttachedFileKind.ANNEX


def test_a_file_plant_takes_another_kind_when_the_sitting_has_no_same_kind(
    scratch_session: Session,
    read_only_scratch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(
        scratch_session,
        4,
        [_FIRST_TRANSCRIPT],
        [AttachedFileKind.ANNEX, AttachedFileKind.VERNACULAR],
    )
    _set_sizes(monkeypatch, 1, 15)

    build_attached_file_check(_ROUND_NUMBER, tmp_path / "check")

    packet_id_to_packet = {
        packet.packet_id: packet for packet in _read_packets(tmp_path / "check").root
    }
    file_plants = [
        plant
        for plant in _read_key(tmp_path / "check").plants
        if plant.kind == AttachedFileCheckPlantKind.FILE
    ]
    assert file_plants
    for plant in file_plants:
        assert (
            packet_id_to_packet[plant.packet_id].file_kind
            == AttachedFileKind.VERNACULAR
        )


def test_a_row_with_nothing_to_swap_to_is_never_planted(
    scratch_session: Session,
    read_only_scratch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    one_row_pointer_ids = _seed(
        scratch_session, 4, [_FIRST_TRANSCRIPT], [AttachedFileKind.ANNEX]
    )
    _set_sizes(monkeypatch, 1, 15)

    build_attached_file_check(_ROUND_NUMBER, tmp_path / "check")

    key = _read_key(tmp_path / "check")
    assert key.plants == []
    assert len(key.packet_id_to_pointer_id) == 1
    assert set(key.packet_id_to_pointer_id.values()) <= set(one_row_pointer_ids)


def test_a_paragraph_plant_takes_a_row_holding_the_link_words_when_there_is_one(
    scratch_session: Session,
    read_only_scratch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(
        scratch_session,
        2,
        [_FIRST_TRANSCRIPT, _OTHER_TRANSCRIPT, _SECOND_LINK_TRANSCRIPT],
        [],
    )
    _set_sizes(monkeypatch, 1, 15)

    build_attached_file_check(_ROUND_NUMBER, tmp_path / "check")

    [plant] = _read_key(tmp_path / "check").plants
    [packet] = [
        packet
        for packet in _read_packets(tmp_path / "check").root
        if packet.packet_id == plant.packet_id
    ]
    assert plant.kind == AttachedFileCheckPlantKind.PARAGRAPH
    assert plant.is_row_holding_link_words is True
    assert packet.speech_ordinal == _THIRD_ORDINAL


def test_a_paragraph_plant_falls_back_to_any_other_row(
    scratch_session: Session,
    read_only_scratch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(scratch_session, 2, [_FIRST_TRANSCRIPT, _OTHER_TRANSCRIPT], [])
    _set_sizes(monkeypatch, 1, 15)

    build_attached_file_check(_ROUND_NUMBER, tmp_path / "check")

    [plant] = _read_key(tmp_path / "check").plants
    [packet] = [
        packet
        for packet in _read_packets(tmp_path / "check").root
        if packet.packet_id == plant.packet_id
    ]
    assert plant.is_row_holding_link_words is False
    assert plant.true_speech_ordinal == 1
    assert packet.speech_ordinal == _SECOND_ORDINAL


def test_no_batch_file_holds_a_tier_name_or_a_report_key(
    scratch_session: Session,
    read_only_scratch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(
        scratch_session,
        6,
        [_FIRST_TRANSCRIPT, _OTHER_TRANSCRIPT],
        [AttachedFileKind.ANNEX, AttachedFileKind.ANNEX],
    )
    _set_sizes(monkeypatch, 3, 1)

    build_attached_file_check(_ROUND_NUMBER, tmp_path / "check")

    batch_paths = sorted((tmp_path / "check" / "batches").rglob("*.md"))
    assert {batch_path.parent.name for batch_path in batch_paths} == {"sonnet", "opus"}
    for batch_path in batch_paths:
        batch_text = batch_path.read_text(encoding="utf-8")
        assert _REPORT_ID_PREFIX not in batch_text
        for tie_rule in ParagraphTieRule:
            assert tie_rule.value not in batch_text
        assert "Packet " in batch_text


def test_batches_are_cut_at_the_packet_limit(
    scratch_session: Session,
    read_only_scratch: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(
        scratch_session,
        _SEEDED_REPORT_COUNT,
        [_FIRST_TRANSCRIPT],
        [AttachedFileKind.ANNEX],
    )
    _set_sizes(monkeypatch, 50, 0)
    monkeypatch.setattr(build_attached_file_check_script, "_MAX_PACKETS_PER_BATCH", 2)

    build_attached_file_check(_ROUND_NUMBER, tmp_path / "check")

    assert [
        batch_path.name
        for batch_path in sorted((tmp_path / "check" / "batches" / "opus").iterdir())
    ] == ["packets-001.md", "packets-002.md", "packets-003.md"]


def test_an_existing_output_directory_refuses(
    scratch_session: Session, read_only_scratch: None, tmp_path: Path
) -> None:
    with pytest.raises(HansardAttachedFileError):
        build_attached_file_check(_ROUND_NUMBER, tmp_path)


def test_the_paragraph_text_is_the_enclosing_paragraph() -> None:
    content = (
        '<p>First <a href="/search/search/download?value=20230301/annex-A.pdf">A</a></p>'
        '<p>Second <a href="/search/search/download?value=20230301/annex-B.pdf">B</a></p>'
    )

    assert get_pointer_paragraph_text(content, 2) == "Second B"


def test_the_paragraph_text_is_the_parent_text_without_a_paragraph() -> None:
    content = '<div>Plain <a href="/search/search/download?value=20230301/annex-A.pdf">A</a></div>'

    assert get_pointer_paragraph_text(content, 1) == "Plain A"


def test_the_paragraph_text_is_cut_around_its_own_pointer() -> None:
    link = '<a href="/search/search/download?value=20230301/annex-{name}.pdf">Annex</a>'
    content = (
        f"<div>{'start ' * 500}{link.format(name='A')}{'middle ' * 500}"
        f"second-side {link.format(name='B')} first-side{' end' * 500}</div>"
    )

    paragraph_text = get_pointer_paragraph_text(content, 2)

    assert len(paragraph_text) == _CUT_PARAGRAPH_LENGTH
    assert "second-side Annex first-side" in paragraph_text
    assert "start" not in paragraph_text


def test_a_pointer_number_beyond_the_links_raises() -> None:
    content = (
        '<p><a href="/search/search/download?value=20230301/annex-A.pdf">A</a></p>'
    )

    with pytest.raises(HansardAttachedFileError):
        get_pointer_paragraph_text(content, 2)
