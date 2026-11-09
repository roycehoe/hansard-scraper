import hashlib
import random
import re
from collections.abc import MutableSequence
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import NoReturn, Optional

import pytest
from sqlmodel import Session

import scripts.draw_law_link_check as draw_law_link_check_script
from crud.act_history_entry import ActHistoryEntryRow
from crud.bill import BillRow
from crud.bill_key import BillKeyRow
from crud.bill_report import BillReportSittingDateReportTypeRow
from crud.bill_report_speaker import BillReportSpeakerRow
from crud.bill_stage_line import BillStageLineRow
from crud.report import ReportPlacementRow
from crud.speech import SpeechParseRow
from database.act import Act, ActHistoryEntry
from enums import (
    ActHistoryEntryKind,
    BillLinkSource,
    BillReportRole,
    BillStage,
    LawLinkCheckRule,
    SpeechKind,
)
from exceptions import HansardLawLinkCheckError
from populate.bill_speakers import get_bill_speaker_plan, write_bill_speaker_plan
from schemas.law_link_check_packet import LawLinkCheckPacket
from schemas.law_link_check_plant_key import LawLinkCheckPlant, LawLinkCheckPlantKey
from scripts.draw_law_link_check import (
    LawLinkCheck,
    LawLinkCheckCandidate,
    LawLinkCheckInputs,
    LawLinkCheckTexts,
    get_batches,
    get_candidates,
    get_drawn_candidates,
    get_law_link_check,
    get_packet_ids,
    get_planted_choices,
    get_rule_lines,
    get_rule_planted_choices,
    render_packet,
    write_law_link_check_files,
)
from tests.bill_seed import (
    BILL_SPEECHES_FIRST_SPRS_REPORT_ID,
    BILL_SPEECHES_THIRD_SPRS_REPORT_ID,
    SPEAKER_A_LABEL,
    seed_bill_speeches,
)
from utils.title_key import get_title_key

_SEED = 7
_OTHER_SEED = 8
_GROUP = "1960s bill"
_REPORT_TYPE = "bill"
_SITTING_DATE = datetime(1964, 11, 19)
_GROUP_SAMPLE_SIZE = 50
_OVER_SAMPLE_SIZE = 120
_RULE_ROW_COUNT = 60
_PLANTS_PER_RULE = 5
_EXPECTED_PLANT_COUNT = 45
_PACKET_ID_PATTERN = re.compile(r"[0-9a-f]{12}")
_SHORT_PACKET_COUNT = 51
_LONG_PACKET_LENGTH = 50_000
_SEEDED_MEMBER_PACKET_COUNT = 3
_SEEDED_STAGE_PACKET_COUNT = 3
_PLACEMENT_REPORT_IDS = (1, 2)
_STAGE_ROW_COUNT = 12
_OTHER_STAGE_ROW_COUNT = 4
_DRAWN_STAGE_ROW_COUNT = 3
_MEMBER_ROW_COUNT = 6
_LONE_MEMBER_ROW_ID = 7
_ACT_ROW_COUNT = 6
_HAND_KEPT_ROW_COUNT = 3
_FIRST_READING_ROW_COUNT = 9
_ALLOWED_GAPS = frozenset({2, 3})


class _RandomOnlyGenerator(random.Random):
    def randrange(
        self, start: int, stop: Optional[int] = None, step: int = 1
    ) -> NoReturn:
        pytest.fail("randrange was called")

    def choice(self, seq: object) -> NoReturn:
        pytest.fail("choice was called")

    def sample(self, population: object, k: int, **keyword_arguments: object) -> list:
        pytest.fail("sample was called")

    def shuffle(self, x: MutableSequence[object]) -> None:
        pytest.fail("shuffle was called")


def _build_inputs(**changes: object) -> LawLinkCheckInputs:
    return replace(LawLinkCheckInputs({}, {}, {}, {}, {}, {}, {}, {}), **changes)


def _build_bill(bill_id: int, title: str) -> BillRow:
    return BillRow(
        bill_id,
        title,
        get_title_key(title),
        _SITTING_DATE,
        _SITTING_DATE,
        True,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def _build_bill_report_row(
    bill_id: int, report_id: int, sprs_report_id: str
) -> BillReportSittingDateReportTypeRow:
    return BillReportSittingDateReportTypeRow(
        bill_id,
        report_id,
        sprs_report_id,
        _SITTING_DATE,
        _REPORT_TYPE,
        BillReportRole.READING,
    )


def _build_entry_row(
    entry_id: int, bill_link_source: Optional[BillLinkSource], bill_id: Optional[int]
) -> ActHistoryEntryRow:
    return ActHistoryEntryRow(
        entry_id,
        1,
        entry_id,
        f"Entry {entry_id} printed text",
        "1",
        f"Entry {entry_id}",
        None,
        date(1964, 11, 19),
        None,
        date(1965, 6, 16),
        None,
        ActHistoryEntryKind.ORDINANCE,
        bill_link_source,
        bill_id,
    )


def _build_member_row(
    member_id: int, sprs_report_id: str, speaker_id: int
) -> BillReportSpeakerRow:
    return BillReportSpeakerRow(
        member_id, 1, member_id, "Ms A", sprs_report_id, speaker_id
    )


def _build_stage_row(
    stage_line_id: int, stage: BillStage, sprs_report_id: str = "r1"
) -> BillStageLineRow:
    return BillStageLineRow(
        stage_line_id, stage, f"Line {stage_line_id}", stage_line_id, sprs_report_id
    )


def _build_report_inputs(**changes: object) -> LawLinkCheckInputs:
    return _build_inputs(
        **{
            "bill_id_to_bill": {
                1: _build_bill(1, "ALPHA BILL"),
                2: _build_bill(2, "BETA BILL"),
            },
            "bill_id_to_bill_key": {
                1: BillKeyRow(1, "r1", 0, 1),
                2: BillKeyRow(2, "r2", 0, 2),
            },
            "bill_id_to_bill_report_rows": {
                1: [_build_bill_report_row(1, 1, "r1")],
                2: [_build_bill_report_row(2, 2, "r2")],
            },
            "sprs_report_id_to_bill_report_row": {
                "r1": _build_bill_report_row(1, 1, "r1"),
                "r2": _build_bill_report_row(2, 2, "r2"),
            },
            "speaker_id_to_name": {1: "Ms A", 2: "Mr B"},
            **changes,
        }
    )


def _build_candidates(
    rule: LawLinkCheckRule, row_ids: range
) -> list[LawLinkCheckCandidate]:
    return [LawLinkCheckCandidate(rule, _GROUP, row_id) for row_id in row_ids]


def _build_act_entries(
    bill_link_source: BillLinkSource, row_ids: range
) -> dict[int, ActHistoryEntryRow]:
    return {
        row_id: _build_entry_row(row_id, bill_link_source, row_id % 2 + 1)
        for row_id in row_ids
    }


def _build_large_inputs() -> LawLinkCheckInputs:
    act_history_entry_id_to_row: dict[int, ActHistoryEntryRow] = {}
    for rule_index, bill_link_source in enumerate(
        (
            BillLinkSource.FIRST_READING_DATE,
            BillLinkSource.THIRD_READING_DATE,
            BillLinkSource.LOOSE_TITLE_READING_DATES,
            BillLinkSource.HAND_KEPT,
        )
    ):
        act_history_entry_id_to_row.update(
            _build_act_entries(
                bill_link_source,
                range(
                    rule_index * _RULE_ROW_COUNT + 1,
                    (rule_index + 1) * _RULE_ROW_COUNT + 1,
                ),
            )
        )
    stages = (
        BillStage.FIRST_READING,
        BillStage.SECOND_READING_ORDER,
        BillStage.SECOND_READING_AGREED,
        BillStage.THIRD_READING,
    )
    return _build_report_inputs(
        act_history_entry_id_to_row=act_history_entry_id_to_row,
        bill_report_speaker_id_to_row={
            member_id: _build_member_row(member_id, "r1", member_id % 2 + 1)
            for member_id in range(1, _RULE_ROW_COUNT + 1)
        },
        bill_stage_line_id_to_row={
            stage_line_id: _build_stage_row(
                stage_line_id, stages[(stage_line_id - 1) // _RULE_ROW_COUNT]
            )
            for stage_line_id in range(1, len(stages) * _RULE_ROW_COUNT + 1)
        },
    )


def _build_large_texts() -> LawLinkCheckTexts:
    return LawLinkCheckTexts(
        report_id_to_placement_row={
            report_id: ReportPlacementRow(
                report_id,
                f"r{report_id}",
                _SITTING_DATE,
                f"Report {report_id}",
                _REPORT_TYPE,
            )
            for report_id in _PLACEMENT_REPORT_IDS
        },
        report_id_and_ordinal_to_speech_row={
            (1, ordinal): SpeechParseRow(
                ordinal, 1, ordinal, "Ms A", f"Line {ordinal}", SpeechKind.SPEECH, 1
            )
            for ordinal in range(1, _RULE_ROW_COUNT + 1)
        },
    )


def _seed_law_links(session: Session) -> None:
    seeded = seed_bill_speeches(session)
    write_bill_speaker_plan(session, get_bill_speaker_plan(session))
    act = Act(sso_code="FA2025", title="Food Act 2025")
    session.add(act)
    session.flush()
    assert act.id is not None
    session.add(
        ActHistoryEntry(
            ordinal=1,
            printed_text="Food Act 2025 first reading 12 November 2024",
            printed_law_number="1",
            printed_title="Food Act 2025",
            first_reading_date=date(2024, 11, 12),
            third_reading_date=date(2025, 1, 8),
            kind=ActHistoryEntryKind.ACT,
            bill_link_source=BillLinkSource.FIRST_READING_DATE,
            act_id=act.id,
            bill_id=seeded.bill_id,
        )
    )
    session.commit()


def test_a_group_of_fifty_or_fewer_is_drawn_whole() -> None:
    candidates = _build_candidates(
        LawLinkCheckRule.MEMBER, range(1, _GROUP_SAMPLE_SIZE + 1)
    )

    drawn_candidates = get_drawn_candidates(candidates, random.Random(_SEED))

    assert drawn_candidates == candidates


def test_a_group_over_fifty_is_drawn_as_fifty_evenly_spaced_rows() -> None:
    candidates = _build_candidates(
        LawLinkCheckRule.MEMBER, range(1, _OVER_SAMPLE_SIZE + 1)
    )

    drawn_candidates = get_drawn_candidates(candidates, random.Random(_SEED))

    row_ids = [candidate.row_id for candidate in drawn_candidates]
    assert len(row_ids) == _GROUP_SAMPLE_SIZE
    gaps = {later - earlier for earlier, later in zip(row_ids, row_ids[1:])}
    assert gaps <= _ALLOWED_GAPS
    assert row_ids[-1] <= _OVER_SAMPLE_SIZE


def test_each_rule_is_drawn_alone() -> None:
    first_rule_candidates = _build_candidates(
        LawLinkCheckRule.MEMBER, range(1, _RULE_ROW_COUNT + 1)
    )
    second_rule_candidates = _build_candidates(
        LawLinkCheckRule.STAGE_FIRST_READING, range(101, 101 + _RULE_ROW_COUNT)
    )

    drawn_candidates = get_drawn_candidates(
        first_rule_candidates + second_rule_candidates, random.Random(_SEED)
    )

    drawn_member_ids = {
        candidate.row_id
        for candidate in drawn_candidates
        if candidate.rule == LawLinkCheckRule.MEMBER
    }
    drawn_stage_ids = {
        candidate.row_id
        for candidate in drawn_candidates
        if candidate.rule == LawLinkCheckRule.STAGE_FIRST_READING
    }
    assert len(drawn_member_ids) == _GROUP_SAMPLE_SIZE
    assert len(drawn_stage_ids) == _GROUP_SAMPLE_SIZE
    assert drawn_member_ids.isdisjoint(drawn_stage_ids)


def test_the_same_seed_draws_the_same_rows_and_another_seed_draws_other_starts() -> (
    None
):
    candidates = _build_candidates(
        LawLinkCheckRule.MEMBER, range(1, _OVER_SAMPLE_SIZE + 1)
    )

    first_draw = get_drawn_candidates(candidates, random.Random(_SEED))
    second_draw = get_drawn_candidates(candidates, random.Random(_SEED))
    other_draw = get_drawn_candidates(candidates, random.Random(_OTHER_SEED))

    assert first_draw == second_draw
    assert first_draw != other_draw


def test_the_draw_calls_only_random_on_the_generator() -> None:
    inputs = _build_large_inputs()
    generator = _RandomOnlyGenerator(_SEED)

    candidates = get_candidates(inputs)
    drawn_candidates = get_drawn_candidates(candidates, generator)
    planted_choices = get_planted_choices(
        candidates, drawn_candidates, inputs, generator
    )
    packet_ids = get_packet_ids(len(planted_choices), generator)

    assert len(planted_choices) == _EXPECTED_PLANT_COUNT
    assert len(packet_ids) == _EXPECTED_PLANT_COUNT


def test_an_act_group_is_the_decade_of_the_first_sitting_date_and_the_key_report_type() -> (
    None
):
    inputs = _build_report_inputs(
        act_history_entry_id_to_row={
            1: _build_entry_row(1, BillLinkSource.HAND_KEPT, 1)
        }
    )

    assert get_candidates(inputs) == [
        LawLinkCheckCandidate(LawLinkCheckRule.ACT_HAND_KEPT, _GROUP, 1)
    ]


def test_an_entry_labelled_second_reading_date_is_not_a_candidate() -> None:
    inputs = _build_report_inputs(
        act_history_entry_id_to_row={
            1: _build_entry_row(1, BillLinkSource.SECOND_READING_DATE, 1)
        }
    )

    assert get_candidates(inputs) == []


def test_a_similar_title_label_refuses_the_draw() -> None:
    inputs = _build_report_inputs(
        act_history_entry_id_to_row={
            1: _build_entry_row(1, BillLinkSource.SIMILAR_TITLE_READING_DATES, 1)
        }
    )

    with pytest.raises(HansardLawLinkCheckError, match="apply_hand_kept_act_links"):
        get_candidates(inputs)


def test_an_act_link_to_a_bill_with_no_key_row_is_refused() -> None:
    inputs = _build_report_inputs(
        act_history_entry_id_to_row={
            1: _build_entry_row(1, BillLinkSource.HAND_KEPT, 1)
        },
        bill_id_to_bill_key={},
    )

    with pytest.raises(HansardLawLinkCheckError, match="run apply_bill_speakers first"):
        get_candidates(inputs)


def test_a_member_row_in_a_report_no_bill_holds_is_refused() -> None:
    inputs = _build_inputs(
        bill_report_speaker_id_to_row={1: _build_member_row(1, "unheld", 1)}
    )

    with pytest.raises(HansardLawLinkCheckError, match="no bill holds the report"):
        get_candidates(inputs)


def test_each_stage_has_its_own_rule() -> None:
    inputs = _build_report_inputs(
        bill_stage_line_id_to_row={
            1: _build_stage_row(1, BillStage.FIRST_READING),
            2: _build_stage_row(2, BillStage.SECOND_READING_ORDER),
            3: _build_stage_row(3, BillStage.SECOND_READING_AGREED),
            4: _build_stage_row(4, BillStage.THIRD_READING),
        }
    )

    assert [candidate.rule for candidate in get_candidates(inputs)] == [
        LawLinkCheckRule.STAGE_FIRST_READING,
        LawLinkCheckRule.STAGE_SECOND_READING_ORDER,
        LawLinkCheckRule.STAGE_SECOND_READING_AGREED,
        LawLinkCheckRule.STAGE_THIRD_READING,
    ]


def test_a_stage_plant_claims_a_line_of_another_stage_from_outside_the_sample() -> None:
    first_reading_ids = range(1, _STAGE_ROW_COUNT + 1)
    third_reading_ids = range(
        _STAGE_ROW_COUNT + 1, _STAGE_ROW_COUNT + _OTHER_STAGE_ROW_COUNT + 1
    )
    inputs = _build_report_inputs(
        bill_stage_line_id_to_row={
            **{
                row_id: _build_stage_row(row_id, BillStage.FIRST_READING)
                for row_id in first_reading_ids
            },
            **{
                row_id: _build_stage_row(row_id, BillStage.THIRD_READING)
                for row_id in third_reading_ids
            },
        }
    )
    candidates = get_candidates(inputs)
    drawn_candidates = [
        candidate
        for candidate in candidates
        if candidate.rule == LawLinkCheckRule.STAGE_FIRST_READING
        and candidate.row_id <= _DRAWN_STAGE_ROW_COUNT
    ]

    planted_choices = get_rule_planted_choices(
        LawLinkCheckRule.STAGE_FIRST_READING,
        candidates,
        drawn_candidates,
        inputs,
        random.Random(_SEED),
    )

    assert len(planted_choices) == _PLANTS_PER_RULE
    for planted_choice in planted_choices:
        assert planted_choice.candidate not in drawn_candidates
        assert (
            inputs.bill_stage_line_id_to_row[planted_choice.claimed_row_id].stage
            != BillStage.FIRST_READING
        )


def test_a_member_plant_claims_another_member_of_the_same_report() -> None:
    member_rows = {
        member_id: _build_member_row(member_id, "r1", member_id % 2 + 1)
        for member_id in range(1, _MEMBER_ROW_COUNT + 1)
    }
    member_rows[_LONE_MEMBER_ROW_ID] = _build_member_row(_LONE_MEMBER_ROW_ID, "r2", 1)
    inputs = _build_report_inputs(bill_report_speaker_id_to_row=member_rows)
    candidates = get_candidates(inputs)

    planted_choices = get_rule_planted_choices(
        LawLinkCheckRule.MEMBER, candidates, [], inputs, random.Random(_SEED)
    )

    assert len(planted_choices) == _PLANTS_PER_RULE
    for planted_choice in planted_choices:
        source_row = member_rows[planted_choice.candidate.row_id]
        claimed_row = member_rows[planted_choice.claimed_row_id]
        assert planted_choice.candidate.row_id != _LONE_MEMBER_ROW_ID
        assert claimed_row.sprs_report_id == source_row.sprs_report_id
        assert claimed_row.speaker_id != source_row.speaker_id


def test_an_act_plant_claims_a_bill_of_another_title() -> None:
    entry_rows = _build_act_entries(
        BillLinkSource.FIRST_READING_DATE, range(1, _ACT_ROW_COUNT + 1)
    )
    inputs = _build_report_inputs(act_history_entry_id_to_row=entry_rows)
    candidates = get_candidates(inputs)

    planted_choices = get_rule_planted_choices(
        LawLinkCheckRule.ACT_FIRST_READING_DATE,
        candidates,
        [],
        inputs,
        random.Random(_SEED),
    )

    assert len(planted_choices) == _PLANTS_PER_RULE
    for planted_choice in planted_choices:
        source_bill_id = entry_rows[planted_choice.candidate.row_id].bill_id
        claimed_bill_id = entry_rows[planted_choice.claimed_row_id].bill_id
        assert source_bill_id is not None
        assert claimed_bill_id is not None
        assert (
            inputs.bill_id_to_bill[claimed_bill_id].title_key
            != inputs.bill_id_to_bill[source_bill_id].title_key
        )


def test_a_rule_whose_rows_are_all_drawn_takes_act_plants_from_first_reading_entries() -> (
    None
):
    entry_rows = {
        **_build_act_entries(
            BillLinkSource.HAND_KEPT, range(1, _HAND_KEPT_ROW_COUNT + 1)
        ),
        **_build_act_entries(
            BillLinkSource.FIRST_READING_DATE,
            range(
                _HAND_KEPT_ROW_COUNT + 1,
                _HAND_KEPT_ROW_COUNT + _FIRST_READING_ROW_COUNT + 1,
            ),
        ),
    }
    inputs = _build_report_inputs(act_history_entry_id_to_row=entry_rows)
    candidates = get_candidates(inputs)
    drawn_candidates = [
        candidate
        for candidate in candidates
        if candidate.rule == LawLinkCheckRule.ACT_HAND_KEPT
    ]

    planted_choices = get_rule_planted_choices(
        LawLinkCheckRule.ACT_HAND_KEPT,
        candidates,
        drawn_candidates,
        inputs,
        random.Random(_SEED),
    )

    assert len(planted_choices) == _PLANTS_PER_RULE
    for planted_choice in planted_choices:
        assert planted_choice.candidate.rule == LawLinkCheckRule.ACT_FIRST_READING_DATE
        assert planted_choice.rule == LawLinkCheckRule.ACT_HAND_KEPT


def test_a_rule_with_no_row_outside_the_sample_raises() -> None:
    inputs = _build_report_inputs(
        bill_stage_line_id_to_row={
            1: _build_stage_row(1, BillStage.FIRST_READING),
            2: _build_stage_row(2, BillStage.FIRST_READING),
            3: _build_stage_row(3, BillStage.THIRD_READING),
        }
    )
    candidates = get_candidates(inputs)

    with pytest.raises(HansardLawLinkCheckError, match="No row is left to plant"):
        get_rule_planted_choices(
            LawLinkCheckRule.STAGE_FIRST_READING,
            candidates,
            candidates,
            inputs,
            random.Random(_SEED),
        )


def test_a_rendered_packet_shows_no_sprs_report_id(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_law_links(scratch_session)
    monkeypatch.setattr(draw_law_link_check_script, "_PLANTS_PER_RULE", 0)

    law_link_check = get_law_link_check(scratch_session, _SEED)

    assert law_link_check.packets
    for packet in law_link_check.packets:
        rendered_packet = render_packet(packet)
        assert BILL_SPEECHES_FIRST_SPRS_REPORT_ID not in rendered_packet
        assert BILL_SPEECHES_THIRD_SPRS_REPORT_ID not in rendered_packet
        packet_ids = re.findall(r"## Packet (\S+)", rendered_packet)
        assert len(packet_ids) == 1
        assert _PACKET_ID_PATTERN.fullmatch(packet_ids[0])


def test_the_seeded_schema_gives_member_stage_and_act_packets(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_law_links(scratch_session)
    monkeypatch.setattr(draw_law_link_check_script, "_PLANTS_PER_RULE", 0)

    packets = get_law_link_check(scratch_session, _SEED).packets

    member_packets = [
        packet for packet in packets if packet.rule == LawLinkCheckRule.MEMBER
    ]
    stage_rules = [
        packet.rule for packet in packets if packet.rule.value.startswith("STAGE_")
    ]
    act_packets = [
        packet
        for packet in packets
        if packet.rule == LawLinkCheckRule.ACT_FIRST_READING_DATE
    ]
    assert len(member_packets) == _SEEDED_MEMBER_PACKET_COUNT
    assert sorted(stage_rules) == sorted(
        [
            LawLinkCheckRule.STAGE_FIRST_READING,
            LawLinkCheckRule.STAGE_SECOND_READING_AGREED,
            LawLinkCheckRule.STAGE_THIRD_READING,
        ]
    )
    assert len(stage_rules) == _SEEDED_STAGE_PACKET_COUNT
    assert [packet.group for packet in act_packets] == ["2020s bill-intro"]
    assert any(
        f"{SPEAKER_A_LABEL}: I support the Bill." in packet.source_text
        for packet in member_packets
    )


def test_the_plant_key_names_every_plant_and_the_packet_record_does_not(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        draw_law_link_check_script,
        "read_law_link_check_inputs",
        lambda session: _build_large_inputs(),
    )
    monkeypatch.setattr(
        draw_law_link_check_script,
        "read_law_link_check_texts",
        lambda session, requests, inputs: _build_large_texts(),
    )

    law_link_check = get_law_link_check(scratch_session, _SEED)

    packet_ids = {packet.packet_id for packet in law_link_check.packets}
    assert len(law_link_check.plant_key.plants) == _EXPECTED_PLANT_COUNT
    for plant in law_link_check.plant_key.plants:
        assert plant.packet_id in packet_ids
        assert plant.original != plant.planted
    assert "is_planted" not in LawLinkCheckPacket.model_fields


def test_the_batches_cut_at_fifty_packets_or_eighty_thousand_characters() -> None:
    short_batches = get_batches(["packet"] * _SHORT_PACKET_COUNT)
    long_batches = get_batches(["x" * _LONG_PACKET_LENGTH, "y" * _LONG_PACKET_LENGTH])

    assert [len(batch) for batch in short_batches] == [_GROUP_SAMPLE_SIZE, 1]
    assert len(long_batches) == len(["x", "y"])


def test_the_rule_lines_give_one_line_per_rule_in_enum_order() -> None:
    candidates = _build_candidates(LawLinkCheckRule.MEMBER, range(1, 4))

    rule_lines = get_rule_lines(candidates, candidates, [])

    assert rule_lines[0] == "rule\tcandidates\tgroups\tdrawn\tplants"
    assert [line.split("\t")[0] for line in rule_lines[1:]] == [
        rule.value for rule in LawLinkCheckRule
    ]
    assert "MEMBER\t3\t1\t3\t0" in rule_lines


def test_the_key_hash_file_holds_the_sha256_of_the_key_file_and_a_second_draw_leaves_the_first_files(
    tmp_path: Path,
) -> None:
    law_link_check = LawLinkCheck(
        [
            LawLinkCheckPacket(
                packet_id="0123456789ab",
                rule=LawLinkCheckRule.MEMBER,
                group=_GROUP,
                row_id=1,
                source_text="Source",
                data_says="Data",
                rule_text="Rule",
            )
        ],
        LawLinkCheckPlantKey(
            plants=[
                LawLinkCheckPlant(
                    packet_id="0123456789ab",
                    rule=LawLinkCheckRule.MEMBER,
                    original="Ms A",
                    planted="Mr B",
                )
            ]
        ),
        [],
    )
    output_directory = tmp_path / "output"
    key_path = tmp_path / "key.json"
    hash_path = tmp_path / "key.sha256"
    write_law_link_check_files(
        law_link_check, ["summary"], output_directory, key_path, hash_path
    )
    packets_path = output_directory / "records" / "packets.json"
    first_packets_text = packets_path.read_text(encoding="utf-8")

    assert (
        hash_path.read_text(encoding="utf-8")
        == hashlib.sha256(key_path.read_bytes()).hexdigest() + "\n"
    )
    with pytest.raises(FileExistsError):
        write_law_link_check_files(
            law_link_check, ["summary"], output_directory, key_path, hash_path
        )
    assert packets_path.read_text(encoding="utf-8") == first_packets_text


def test_the_draw_script_opens_no_write_session() -> None:
    script_text = Path(draw_law_link_check_script.__file__).read_text(encoding="utf-8")

    assert "validate_can_write" not in script_text
    assert "database.init import engine" not in script_text
    assert "build_read_only_engine" in script_text
