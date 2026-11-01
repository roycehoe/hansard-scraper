import random
from collections.abc import Iterator
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Optional, cast

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import ClauseElement
from sqlmodel import Session

import scripts.draw_hand_check_sample as draw_hand_check_sample_script
from crud.speech import CRUDSpeech, SpeechFrameRow, SpeechParseRow, SpeechSnapshotRow
from database.speaker import Speaker
from enums import ReportType, ReportVersion, SpeechKind
from exceptions import HansardHandCheckError
from schemas.hand_check_snapshot import HandCheckFrameSummary

_SEED = 20_261_102
_FIRST_GROUP = "Parliaments 0 to 11"
_SECOND_GROUP = "Parliament 12"
_SPEAKER_ID = 77
_SPEECH_ID = 900
_PERSON_ID = 5
_FRAME_ORDER_BY = (
    'report.parliament_number, report.report_version COLLATE "C", '
    'report.report_type COLLATE "C", report.sitting_date, '
    'report.report_id COLLATE "C", speech.ordinal, speech.id'
)


class _FakeSession:
    def __init__(self) -> None:
        self.statement: Optional[ClauseElement] = None

    def exec(self, statement: ClauseElement) -> Iterator[tuple[int, int]]:
        self.statement = statement
        return iter(())


def _build_frame_rows(
    speech_ids: list[int], parliament_number: int = 12
) -> list[SpeechFrameRow]:
    return [
        SpeechFrameRow(id=speech_id, parliament_number=parliament_number)
        for speech_id in speech_ids
    ]


def _build_speech_snapshot_row(speaker_id: Optional[int]) -> SpeechSnapshotRow:
    return SpeechSnapshotRow(
        id=_SPEECH_ID,
        report_id=35_800,
        hansard_report_id="report-a",
        html_file_name=None,
        report_version=ReportVersion.SPRS3,
        report_type=ReportType.MOTION,
        parliament_number=12,
        sitting_date=datetime(2020, 1, 1),
        title="Motion title",
        ordinal=4,
        speaker="Mr Speaker",
        speaker_id=speaker_id,
        kind=SpeechKind.SPEECH,
        transcript="Order, order.",
    )


def _build_parse_row(speech_id: int, report_id: int, ordinal: int) -> SpeechParseRow:
    return SpeechParseRow(
        id=speech_id,
        report_id=report_id,
        ordinal=ordinal,
        speaker=f"Speaker {speech_id}",
        transcript=f"Text {speech_id}",
        kind=SpeechKind.SPEECH,
        speaker_id=None,
    )


def _build_speaker(person_id: Optional[int]) -> Speaker:
    return Speaker(
        id=_SPEAKER_ID,
        name="Pritam Singh",
        party="WP",
        is_legislative_assembly=False,
        parliament_number=14,
        person_id=person_id,
    )


def test_the_frame_read_orders_by_the_p7_key_in_byte_order() -> None:
    fake_session = _FakeSession()

    list(
        CRUDSpeech(cast(Session, fake_session)).get_frame_rows_by_speaker_id_not_null()
    )

    assert fake_session.statement is not None
    compiled_statement = str(
        fake_session.statement.compile(dialect=postgresql.dialect())
    )
    assert compiled_statement.partition("ORDER BY ")[2] == _FRAME_ORDER_BY


def test_the_frame_groups_the_streamed_ids_without_reordering_them() -> None:
    frame_rows = [
        *_build_frame_rows([20, 10], parliament_number=0),
        *_build_frame_rows([30], parliament_number=11),
        *_build_frame_rows([5, 4], parliament_number=12),
        *_build_frame_rows([6], parliament_number=15),
    ]

    frame = draw_hand_check_sample_script.read_frame(frame_rows)

    assert list(frame.group_to_speech_ids.items()) == [
        (_FIRST_GROUP, [20, 10, 30]),
        (_SECOND_GROUP, [5, 4]),
        ("Parliament 15", [6]),
    ]


def test_the_allocation_sums_to_the_sample_size_by_largest_remainder() -> None:
    group_to_frame_count = {
        "first": 5160,
        "second": 830,
        "third": 1330,
        "fourth": 2070,
        "fifth": 620,
    }

    group_to_allocation = draw_hand_check_sample_script.get_allocation(
        group_to_frame_count, 1_000
    )

    assert group_to_allocation == {
        "first": 515,
        "second": 83,
        "third": 133,
        "fourth": 207,
        "fifth": 62,
    }


def test_equal_remainders_go_to_the_group_listed_first() -> None:
    group_to_allocation = draw_hand_check_sample_script.get_allocation(
        {"first": 1, "second": 1, "third": 1}, 2
    )

    assert group_to_allocation == {"first": 1, "second": 1, "third": 0}


def test_the_weight_spread_is_the_largest_weight_over_the_smallest_minus_one() -> None:
    weight_spread = draw_hand_check_sample_script.get_weight_spread(
        {"first": 100, "second": 300}, {"first": 10, "second": 20}
    )

    assert weight_spread == Fraction(1, 2)


def test_the_starts_come_from_one_seeded_generator_in_group_order() -> None:
    group_to_start = draw_hand_check_sample_script.get_group_to_start(
        {"first": 300, "second": 700}, {"first": 3, "second": 7}, _SEED
    )

    generator = random.Random(_SEED)
    assert group_to_start == {
        "first": Fraction(generator.random()) * 100,
        "second": Fraction(generator.random()) * 100,
    }
    assert group_to_start["first"] == Fraction(0.5665188660199811) * 100


def test_the_same_seed_gives_the_same_starts() -> None:
    group_to_frame_count = {"first": 300, "second": 700}
    group_to_allocation = {"first": 3, "second": 7}

    assert draw_hand_check_sample_script.get_group_to_start(
        group_to_frame_count, group_to_allocation, _SEED
    ) == draw_hand_check_sample_script.get_group_to_start(
        group_to_frame_count, group_to_allocation, _SEED
    )


def test_positions_equal_floor_of_start_plus_pick_times_interval() -> None:
    positions = draw_hand_check_sample_script.get_group_positions(10, 4, Fraction(1, 3))

    assert positions == [0, 2, 5, 7]


def test_the_largest_start_still_picks_inside_the_group() -> None:
    positions = draw_hand_check_sample_script.get_group_positions(
        10, 4, Fraction(5, 2) - Fraction(1, 1_000)
    )

    assert positions == [2, 4, 7, 9]


def test_each_drawn_row_is_the_frame_row_at_its_frame_position_in_its_group() -> None:
    drawn_rows = draw_hand_check_sample_script.get_drawn_rows(
        {_FIRST_GROUP: [11, 12, 13, 14], _SECOND_GROUP: [15, 16]},
        {_FIRST_GROUP: 2, _SECOND_GROUP: 1},
        {_FIRST_GROUP: Fraction(1, 2), _SECOND_GROUP: Fraction(1, 4)},
    )

    assert drawn_rows == [
        draw_hand_check_sample_script.DrawnRow(11, _FIRST_GROUP, 0),
        draw_hand_check_sample_script.DrawnRow(13, _FIRST_GROUP, 2),
        draw_hand_check_sample_script.DrawnRow(15, _SECOND_GROUP, 4),
    ]


def test_the_frame_hash_is_the_sha256_of_the_ids_one_per_line_in_stream_order() -> None:
    frame = draw_hand_check_sample_script.read_frame(_build_frame_rows([1, 2, 3]))

    assert (
        frame.frame_hash
        == "14c5e74c4b96ccef41cd94db73a9ec3348038ac094feca4fd897cecffa07cdae"
    )


def test_the_frame_hash_changes_when_the_order_of_the_ids_changes() -> None:
    in_order = draw_hand_check_sample_script.read_frame(_build_frame_rows([1, 2, 3]))
    reversed_order = draw_hand_check_sample_script.read_frame(
        _build_frame_rows([3, 2, 1])
    )

    assert reversed_order.frame_hash != in_order.frame_hash


def test_a_main_draw_over_the_weight_spread_limit_is_refused() -> None:
    with pytest.raises(HansardHandCheckError, match="weights spread by 31/1000"):
        draw_hand_check_sample_script.validate_can_write_draw(
            {"first": 10, "second": 10}, 20, Fraction(31, 1_000), False
        )


def test_a_main_draw_at_the_weight_spread_limit_is_allowed() -> None:
    draw_hand_check_sample_script.validate_can_write_draw(
        {"first": 10, "second": 10}, 20, Fraction(3, 100), False
    )


def test_a_pilot_draw_over_the_weight_spread_limit_is_recorded_not_refused() -> None:
    draw_hand_check_sample_script.validate_can_write_draw(
        {"first": 10, "second": 10}, 20, Fraction(1, 2), True
    )


@pytest.mark.parametrize("is_pilot", [False, True])
def test_an_allocation_that_misses_the_sample_size_is_refused(is_pilot: bool) -> None:
    with pytest.raises(HansardHandCheckError, match="allocation sums to 19, not 20"):
        draw_hand_check_sample_script.validate_can_write_draw(
            {"first": 10, "second": 9}, 20, Fraction(0), is_pilot
        )


def test_the_next_row_never_crosses_a_report_boundary() -> None:
    first_report_first = _build_parse_row(1, report_id=10, ordinal=1)
    first_report_last = _build_parse_row(2, report_id=10, ordinal=2)
    second_report_first = _build_parse_row(3, report_id=11, ordinal=1)

    speech_id_to_next_row = draw_hand_check_sample_script.get_speech_id_to_next_row(
        [first_report_first, first_report_last, second_report_first]
    )

    assert speech_id_to_next_row == {1: first_report_last}


def test_a_snapshot_row_carries_the_credited_names_and_the_next_row() -> None:
    next_row = _build_parse_row(901, report_id=35_800, ordinal=5)

    snapshot_row = draw_hand_check_sample_script.build_snapshot_row(
        _build_speech_snapshot_row(_SPEAKER_ID),
        next_row,
        {_SPEAKER_ID: _build_speaker(_PERSON_ID)},
        {_PERSON_ID: "Pritam Singh Canonical"},
    )

    assert snapshot_row.speech_id == _SPEECH_ID
    assert snapshot_row.report_title == "Motion title"
    assert snapshot_row.speaker == "Mr Speaker"
    assert snapshot_row.speaker_name == "Pritam Singh"
    assert snapshot_row.person_name == "Pritam Singh Canonical"
    assert snapshot_row.next_speaker == "Speaker 901"
    assert snapshot_row.next_transcript == "Text 901"


def test_the_last_row_of_a_report_has_no_next_speaker_or_next_transcript() -> None:
    snapshot_row = draw_hand_check_sample_script.build_snapshot_row(
        _build_speech_snapshot_row(_SPEAKER_ID),
        None,
        {_SPEAKER_ID: _build_speaker(_PERSON_ID)},
        {_PERSON_ID: "Pritam Singh Canonical"},
    )

    assert snapshot_row.next_speaker is None
    assert snapshot_row.next_transcript is None


def test_a_speaker_with_no_person_has_no_person_name() -> None:
    snapshot_row = draw_hand_check_sample_script.build_snapshot_row(
        _build_speech_snapshot_row(_SPEAKER_ID),
        None,
        {_SPEAKER_ID: _build_speaker(None)},
        {_PERSON_ID: "Pritam Singh Canonical"},
    )

    assert snapshot_row.person_name is None


def test_a_drawn_row_with_no_speaker_id_is_refused() -> None:
    with pytest.raises(
        HansardHandCheckError, match=f"Drawn speech {_SPEECH_ID} holds no speaker id"
    ):
        draw_hand_check_sample_script.build_snapshot_row(
            _build_speech_snapshot_row(None), None, {}, {}
        )


def test_the_draw_tsv_lists_each_row_with_its_group_and_frame_position() -> None:
    lines = draw_hand_check_sample_script.get_draw_tsv_lines(
        [
            draw_hand_check_sample_script.DrawnRow(11, _FIRST_GROUP, 0),
            draw_hand_check_sample_script.DrawnRow(15, _SECOND_GROUP, 4),
        ]
    )

    assert lines == [
        "speech_id\tgroup\tframe_position",
        "11\tParliaments 0 to 11\t0",
        "15\tParliament 12\t4",
    ]


def test_the_summary_lists_every_frame_summary_field_and_one_line_per_group() -> None:
    frame_summary = HandCheckFrameSummary(
        database_label="db.example.org:6543/hansard",
        read_at=datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc),
        seed=_SEED,
        sample_size=20,
        group_to_frame_count={_FIRST_GROUP: 12, _SECOND_GROUP: 8},
        group_to_allocation={_FIRST_GROUP: 12, _SECOND_GROUP: 8},
        group_to_start={_FIRST_GROUP: "5/4", _SECOND_GROUP: "0"},
        frame_hash="f" * 64,
        weight_spread="0",
    )

    lines = draw_hand_check_sample_script.get_summary_lines(frame_summary)

    assert lines == [
        "database_label: db.example.org:6543/hansard",
        "read_at: 2026-11-02T09:30:00+00:00",
        "seed: 20261102",
        "sample_size: 20",
        "frame_hash: " + "f" * 64,
        "weight_spread: 0",
        "group\tframe_count\tallocation\tstart",
        "Parliaments 0 to 11\t12\t12\t5/4",
        "Parliament 12\t8\t8\t0",
    ]


def test_a_second_main_draw_raises_and_leaves_the_first_files_unchanged(
    tmp_path: Path,
) -> None:
    snapshot_directory = tmp_path / "snapshot"
    record_directory = tmp_path / "record"
    draw_hand_check_sample_script.write_draw_files(
        False,
        snapshot_directory,
        record_directory,
        "first snapshot",
        "first tsv",
        "first summary",
    )

    with pytest.raises(FileExistsError):
        draw_hand_check_sample_script.write_draw_files(
            False,
            snapshot_directory,
            record_directory,
            "second snapshot",
            "second tsv",
            "second summary",
        )

    assert (snapshot_directory / "snapshot.json").read_text(
        encoding="utf-8"
    ) == "first snapshot"
    assert (record_directory / "draw.tsv").read_text(encoding="utf-8") == "first tsv"
    assert (record_directory / "draw-summary.txt").read_text(
        encoding="utf-8"
    ) == "first summary"


def test_a_second_pilot_draw_replaces_the_first_files(tmp_path: Path) -> None:
    draw_hand_check_sample_script.write_draw_files(
        True, tmp_path, tmp_path, "first snapshot", "first tsv", "first summary"
    )

    draw_hand_check_sample_script.write_draw_files(
        True, tmp_path, tmp_path, "second snapshot", "second tsv", "second summary"
    )

    assert (tmp_path / "snapshot.json").read_text(encoding="utf-8") == "second snapshot"
    assert (tmp_path / "draw.tsv").read_text(encoding="utf-8") == "second tsv"
    assert (tmp_path / "draw-summary.txt").read_text(
        encoding="utf-8"
    ) == "second summary"
