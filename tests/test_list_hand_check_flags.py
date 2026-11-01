import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pytest

import scripts.list_hand_check_flags as list_hand_check_flags_script
from enums import (
    HandCheckDifferenceClass,
    HandCheckErrorTier,
    HandCheckFlagReason,
    HandCheckFormOfAddress,
    HandCheckLiveCheckStatus,
    HandCheckMatchStatus,
    HandCheckPlantKind,
    HandCheckSpeakerVerdict,
    SpeechKind,
)
from exceptions import HansardHandCheckError
from schemas.hand_check_flag import HandCheckFlag, HandCheckFlags
from schemas.hand_check_office_holder import HandCheckOfficeHolder
from schemas.hand_check_packet import (
    HandCheckGapCheck,
    HandCheckPacket,
    HandCheckPackets,
    HandCheckRoleSection,
    HandCheckWordDifference,
)
from schemas.hand_check_plant_key import HandCheckPlant, HandCheckPlantKey
from schemas.hand_check_snapshot import HandCheckSnapshotRow
from schemas.hand_check_verdict import HandCheckVerdict

_DIFFERENCE_COUNT = 2
_RERUN_NUMBER = 2


@dataclass(frozen=True)
class _OutputPaths:
    flags_path: Path
    summary_path: Path


def _build_differences(count: int) -> list[HandCheckWordDifference]:
    return [
        HandCheckWordDifference(
            operation="replace", source_words=f"word{index}", row_words=f"wrod{index}"
        )
        for index in range(count)
    ]


def _build_packet(
    packet_id: str,
    speech_id: int,
    match_status: HandCheckMatchStatus = HandCheckMatchStatus.EXACT,
    word_differences: Optional[list[HandCheckWordDifference]] = None,
    gap_check: Optional[HandCheckGapCheck] = None,
    role_section: Optional[HandCheckRoleSection] = None,
    report_id: int = 2,
    live_check_status: Optional[HandCheckLiveCheckStatus] = None,
    live_match_status: Optional[HandCheckMatchStatus] = None,
) -> HandCheckPacket:
    return HandCheckPacket(
        packet_id=packet_id,
        snapshot=HandCheckSnapshotRow(
            speech_id=speech_id,
            report_id=report_id,
            hansard_report_id="r1",
            html_file_name=None,
            report_version="sprs3",
            report_type="oral-answer",
            parliament_number=15,
            sitting_date=datetime(2025, 9, 1),
            report_title="Title",
            ordinal=1,
            speaker="Mr Tan",
            speaker_id=3,
            speaker_name="Tan Wu Meng",
            person_name=None,
            kind=SpeechKind.SPEECH,
            transcript="Some words.",
            next_speaker=None,
            next_transcript=None,
        ),
        official_record_url="https://example.org",
        match_status=match_status,
        matched_source_html="<p>Some words.</p>",
        context_paragraphs=[],
        after_paragraph=None,
        word_differences=word_differences or [],
        gap_check=gap_check,
        role_section=role_section,
        live_check_status=live_check_status,
        live_match_status=live_match_status,
    )


def _build_verdict(
    packet_id: str,
    speaker_verdict: HandCheckSpeakerVerdict = HandCheckSpeakerVerdict.RIGHT,
    difference_classes: Optional[list[HandCheckDifferenceClass]] = None,
) -> HandCheckVerdict:
    return HandCheckVerdict(
        packet_id=packet_id,
        speaker_verdict=speaker_verdict,
        speaker_tier=HandCheckErrorTier.A
        if speaker_verdict == HandCheckSpeakerVerdict.WRONG
        else None,
        note="",
        difference_classes=difference_classes or [],
    )


def _build_right_verdicts(packets: list[HandCheckPacket]) -> list[HandCheckVerdict]:
    return [_build_verdict(packet.packet_id) for packet in packets]


def _build_flag(
    packet_id: str,
    speech_id: int,
    run_number: int,
    reasons: list[HandCheckFlagReason],
    sonnet_speaker_verdict: Optional[HandCheckVerdict],
    opus_speaker_verdict: Optional[HandCheckVerdict],
) -> HandCheckFlag:
    return HandCheckFlag(
        packet_id=packet_id,
        speech_id=speech_id,
        run_number=run_number,
        reasons=reasons,
        sonnet_speaker_verdict=sonnet_speaker_verdict,
        opus_speaker_verdict=opus_speaker_verdict,
        word_differences=[],
        match_status=HandCheckMatchStatus.EXACT,
    )


def _build_plant(speech_id: int, kind: HandCheckPlantKind) -> HandCheckPlant:
    return HandCheckPlant(
        speech_id=speech_id, kind=kind, original="original", planted="planted"
    )


def _write_verdicts(
    directory: Path, batch_name: str, verdicts: list[HandCheckVerdict]
) -> None:
    batch_directory = directory / batch_name
    batch_directory.mkdir(parents=True)
    (batch_directory / "verdicts.jsonl").write_text(
        "".join(f"{verdict.model_dump_json()}\n" for verdict in verdicts),
        encoding="utf-8",
    )


def _write_key(
    tmp_path: Path, round_number: int, plants: list[HandCheckPlant]
) -> list_hand_check_flags_script.PlantKeyPaths:
    key_path = tmp_path / f"key-round-{round_number}.json"
    hash_path = tmp_path / f"key-round-{round_number}.sha256"
    key_bytes = (
        HandCheckPlantKey(round_number=round_number, plants=plants)
        .model_dump_json()
        .encode("utf-8")
    )
    key_path.write_bytes(key_bytes)
    hash_path.write_text(hashlib.sha256(key_bytes).hexdigest() + "\n", encoding="utf-8")
    return list_hand_check_flags_script.PlantKeyPaths(key_path, hash_path)


def _write_reader_verdicts(
    directory: Path, verdicts: Optional[list[HandCheckVerdict]]
) -> Optional[Path]:
    if verdicts is None:
        return None
    _write_verdicts(directory, "batch-001", verdicts)
    return directory


def _list_flags(
    tmp_path: Path,
    packets: list[HandCheckPacket],
    sonnet_verdicts: Optional[list[HandCheckVerdict]],
    opus_verdicts: Optional[list[HandCheckVerdict]],
    run_number: int = 1,
    earlier_flags_path: Optional[Path] = None,
    plant_key_paths: Optional[list_hand_check_flags_script.PlantKeyPaths] = None,
    held_reports_path: Optional[Path] = None,
) -> _OutputPaths:
    records_directory = tmp_path / "records"
    records_directory.mkdir(exist_ok=True)
    packets_path = records_directory / "packets.json"
    packets_path.write_text(
        HandCheckPackets(packets).model_dump_json(), encoding="utf-8"
    )
    sonnet_verdicts_path = _write_reader_verdicts(
        tmp_path / f"sonnet-run-{run_number}", sonnet_verdicts
    )
    opus_verdicts_path = _write_reader_verdicts(
        tmp_path / f"opus-run-{run_number}", opus_verdicts
    )
    output_paths = _OutputPaths(
        tmp_path / f"flags-run-{run_number}.json",
        tmp_path / f"summary-run-{run_number}.txt",
    )
    list_hand_check_flags_script.list_hand_check_flags(
        packets_path,
        sonnet_verdicts_path,
        opus_verdicts_path,
        output_paths.flags_path,
        output_paths.summary_path,
        run_number,
        plant_key_paths,
        earlier_flags_path,
        held_reports_path,
    )
    return output_paths


def _assert_no_output_written(tmp_path: Path, run_number: int) -> None:
    assert not (tmp_path / f"flags-run-{run_number}.json").exists()
    assert not (tmp_path / f"summary-run-{run_number}.txt").exists()


def _get_written_flags(flags_path: Path) -> list[HandCheckFlag]:
    return HandCheckFlags.model_validate_json(
        flags_path.read_text(encoding="utf-8")
    ).root


def _get_summary_lines(summary_path: Path) -> list[str]:
    return summary_path.read_text(encoding="utf-8").splitlines()


def test_a_clean_exact_row_has_no_flag_reason() -> None:
    assert (
        list_hand_check_flags_script.get_flag_reasons(
            _build_packet("k1", 1), _build_verdict("k1"), _build_verdict("k1")
        )
        == []
    )


@pytest.mark.parametrize(
    ("sonnet_speaker_verdict", "opus_speaker_verdict"),
    [
        (HandCheckSpeakerVerdict.WRONG, HandCheckSpeakerVerdict.RIGHT),
        (HandCheckSpeakerVerdict.RECORD_DOES_NOT_SAY, HandCheckSpeakerVerdict.RIGHT),
        (HandCheckSpeakerVerdict.RIGHT, HandCheckSpeakerVerdict.WRONG),
        (HandCheckSpeakerVerdict.RIGHT, HandCheckSpeakerVerdict.RECORD_DOES_NOT_SAY),
    ],
)
def test_either_readers_speaker_verdict_that_is_not_right_adds_the_speaker_verdict_reason(
    sonnet_speaker_verdict: HandCheckSpeakerVerdict,
    opus_speaker_verdict: HandCheckSpeakerVerdict,
) -> None:
    assert list_hand_check_flags_script.get_flag_reasons(
        _build_packet("k1", 1),
        _build_verdict("k1", sonnet_speaker_verdict),
        _build_verdict("k1", opus_speaker_verdict),
    ) == [HandCheckFlagReason.SPEAKER_VERDICT]


def test_two_readers_that_both_object_add_the_speaker_verdict_reason_once() -> None:
    assert list_hand_check_flags_script.get_flag_reasons(
        _build_packet("k1", 1),
        _build_verdict("k1", HandCheckSpeakerVerdict.WRONG),
        _build_verdict("k1", HandCheckSpeakerVerdict.WRONG),
    ) == [HandCheckFlagReason.SPEAKER_VERDICT]


def test_a_reader_that_was_not_given_adds_no_reason() -> None:
    packet = _build_packet("k1", 1)

    assert (
        list_hand_check_flags_script.get_flag_reasons(
            packet, _build_verdict("k1"), None
        )
        == []
    )
    assert list_hand_check_flags_script.get_flag_reasons(
        packet, _build_verdict("k1", HandCheckSpeakerVerdict.WRONG), None
    ) == [HandCheckFlagReason.SPEAKER_VERDICT]
    assert list_hand_check_flags_script.get_flag_reasons(packet, None, None) == []


def test_a_word_difference_adds_the_text_difference_reason() -> None:
    assert list_hand_check_flags_script.get_flag_reasons(
        _build_packet("k1", 1, word_differences=_build_differences(1)),
        _build_verdict("k1"),
        _build_verdict("k1"),
    ) == [HandCheckFlagReason.TEXT_DIFFERENCE]


@pytest.mark.parametrize(
    "match_status", [HandCheckMatchStatus.INEXACT, HandCheckMatchStatus.NOT_FOUND]
)
def test_a_match_status_that_is_not_exact_adds_the_match_status_reason(
    match_status: HandCheckMatchStatus,
) -> None:
    assert list_hand_check_flags_script.get_flag_reasons(
        _build_packet("k1", 1, match_status),
        _build_verdict("k1"),
        _build_verdict("k1"),
    ) == [HandCheckFlagReason.MATCH_STATUS]


def test_a_live_check_that_differs_adds_the_live_text_differs_reason() -> None:
    differing_packet = _build_packet(
        "k1",
        1,
        live_check_status=HandCheckLiveCheckStatus.DIFFERS,
        live_match_status=HandCheckMatchStatus.EXACT,
    )
    equal_packet = _build_packet(
        "k1", 1, live_check_status=HandCheckLiveCheckStatus.EQUAL
    )

    assert list_hand_check_flags_script.get_flag_reasons(
        differing_packet, _build_verdict("k1"), _build_verdict("k1")
    ) == [HandCheckFlagReason.LIVE_TEXT_DIFFERS]
    assert (
        list_hand_check_flags_script.get_flag_reasons(
            equal_packet, _build_verdict("k1"), _build_verdict("k1")
        )
        == []
    )


def test_reasons_come_in_enum_order_when_several_apply() -> None:
    packet = _build_packet(
        "k1",
        1,
        HandCheckMatchStatus.INEXACT,
        _build_differences(1),
        live_check_status=HandCheckLiveCheckStatus.DIFFERS,
        live_match_status=HandCheckMatchStatus.INEXACT,
    )

    assert list_hand_check_flags_script.get_flag_reasons(
        packet,
        _build_verdict("k1", HandCheckSpeakerVerdict.WRONG),
        _build_verdict("k1"),
    ) == [
        HandCheckFlagReason.SPEAKER_VERDICT,
        HandCheckFlagReason.TEXT_DIFFERENCE,
        HandCheckFlagReason.MATCH_STATUS,
        HandCheckFlagReason.LIVE_TEXT_DIFFERS,
    ]


def test_a_gap_a_role_section_and_an_equal_live_check_add_no_reason() -> None:
    packet = _build_packet(
        "k1",
        1,
        gap_check=HandCheckGapCheck(
            is_next_row=False, skipped_paragraphs=[], next_source_text="Other words."
        ),
        role_section=HandCheckRoleSection(
            is_chair_label=True, office=None, office_holders=[], chair_marks=[]
        ),
        live_check_status=HandCheckLiveCheckStatus.EQUAL,
    )

    assert (
        list_hand_check_flags_script.get_flag_reasons(
            packet, _build_verdict("k1"), _build_verdict("k1")
        )
        == []
    )


def test_the_reason_enum_holds_exactly_the_four_reasons_in_order() -> None:
    assert [reason.value for reason in HandCheckFlagReason] == [
        "SPEAKER_VERDICT",
        "TEXT_DIFFERENCE",
        "MATCH_STATUS",
        "LIVE_TEXT_DIFFERS",
    ]


def test_get_flags_skips_clean_rows_and_carries_the_whole_verdict_lines() -> None:
    word_differences = _build_differences(1)
    clean_packet = _build_packet("k1", 1)
    flagged_packet = _build_packet(
        "k2", 2, HandCheckMatchStatus.INEXACT, word_differences
    )
    sonnet_verdict = _build_verdict(
        "k2", difference_classes=[HandCheckDifferenceClass.COSMETIC]
    )
    opus_verdict = _build_verdict("k2")

    flags = list_hand_check_flags_script.get_flags(
        [clean_packet, flagged_packet],
        {"k1": _build_verdict("k1"), "k2": sonnet_verdict},
        {"k1": _build_verdict("k1"), "k2": opus_verdict},
        1,
    )

    assert flags == [
        HandCheckFlag(
            packet_id="k2",
            speech_id=2,
            run_number=1,
            reasons=[
                HandCheckFlagReason.TEXT_DIFFERENCE,
                HandCheckFlagReason.MATCH_STATUS,
            ],
            sonnet_speaker_verdict=sonnet_verdict,
            opus_speaker_verdict=opus_verdict,
            word_differences=word_differences,
            match_status=HandCheckMatchStatus.INEXACT,
        )
    ]


def test_a_reader_that_was_not_given_has_none_in_the_flag() -> None:
    packet = _build_packet("k1", 1, HandCheckMatchStatus.NOT_FOUND)
    verdict = _build_verdict("k1")

    sonnet_only_flags = list_hand_check_flags_script.get_flags(
        [packet], {"k1": verdict}, None, 2
    )
    opus_only_flags = list_hand_check_flags_script.get_flags(
        [packet], None, {"k1": verdict}, 2
    )

    assert sonnet_only_flags[0].sonnet_speaker_verdict == verdict
    assert sonnet_only_flags[0].opus_speaker_verdict is None
    assert opus_only_flags[0].sonnet_speaker_verdict is None
    assert opus_only_flags[0].opus_speaker_verdict == verdict


def test_a_sonnet_line_on_an_inexact_packet_needs_one_class_per_difference() -> None:
    packet = _build_packet(
        "k1", 1, HandCheckMatchStatus.INEXACT, _build_differences(_DIFFERENCE_COUNT)
    )
    verdict = _build_verdict(
        "k1",
        difference_classes=[
            HandCheckDifferenceClass.COSMETIC,
            HandCheckDifferenceClass.SUBSTANTIVE,
        ],
    )

    assert list_hand_check_flags_script.get_packet_id_to_verdict(
        [packet], [verdict], list_hand_check_flags_script.SONNET_READER
    ) == {"k1": verdict}
    assert (
        list_hand_check_flags_script.get_expected_class_count(
            packet, list_hand_check_flags_script.SONNET_READER
        )
        == _DIFFERENCE_COUNT
    )


@pytest.mark.parametrize("class_count", [0, 1, 3])
def test_a_wrong_class_count_is_refused(class_count: int) -> None:
    packet = _build_packet(
        "k1", 1, HandCheckMatchStatus.INEXACT, _build_differences(_DIFFERENCE_COUNT)
    )
    verdict = _build_verdict(
        "k1", difference_classes=[HandCheckDifferenceClass.COSMETIC] * class_count
    )

    with pytest.raises(
        HansardHandCheckError, match="wrong number of difference classes"
    ):
        list_hand_check_flags_script.get_packet_id_to_verdict(
            [packet], [verdict], list_hand_check_flags_script.SONNET_READER
        )


@pytest.mark.parametrize(
    "match_status", [HandCheckMatchStatus.EXACT, HandCheckMatchStatus.NOT_FOUND]
)
def test_a_sonnet_line_on_any_other_packet_needs_no_class(
    match_status: HandCheckMatchStatus,
) -> None:
    packet = _build_packet("k1", 1, match_status)
    verdict_with_a_class = _build_verdict(
        "k1", difference_classes=[HandCheckDifferenceClass.COSMETIC]
    )
    verdict_with_no_class = _build_verdict("k1")

    with pytest.raises(
        HansardHandCheckError, match="wrong number of difference classes"
    ):
        list_hand_check_flags_script.get_packet_id_to_verdict(
            [packet],
            [verdict_with_a_class],
            list_hand_check_flags_script.SONNET_READER,
        )
    assert list_hand_check_flags_script.get_packet_id_to_verdict(
        [packet], [verdict_with_no_class], list_hand_check_flags_script.SONNET_READER
    ) == {"k1": verdict_with_no_class}
    assert (
        list_hand_check_flags_script.get_expected_class_count(
            packet, list_hand_check_flags_script.SONNET_READER
        )
        == 0
    )


def test_an_opus_line_with_a_class_is_refused() -> None:
    packet = _build_packet(
        "k1", 1, HandCheckMatchStatus.INEXACT, _build_differences(_DIFFERENCE_COUNT)
    )
    verdict_with_classes = _build_verdict(
        "k1",
        difference_classes=[
            HandCheckDifferenceClass.COSMETIC,
            HandCheckDifferenceClass.SUBSTANTIVE,
        ],
    )
    verdict_with_no_class = _build_verdict("k1")

    with pytest.raises(
        HansardHandCheckError, match="wrong number of difference classes"
    ):
        list_hand_check_flags_script.get_packet_id_to_verdict(
            [packet], [verdict_with_classes], list_hand_check_flags_script.OPUS_READER
        )
    assert list_hand_check_flags_script.get_packet_id_to_verdict(
        [packet], [verdict_with_no_class], list_hand_check_flags_script.OPUS_READER
    ) == {"k1": verdict_with_no_class}
    assert (
        list_hand_check_flags_script.get_expected_class_count(
            packet, list_hand_check_flags_script.OPUS_READER
        )
        == 0
    )


def test_the_unknown_repeated_and_missing_checks_come_before_the_class_count() -> None:
    packets = [
        _build_packet(
            "k1",
            1,
            HandCheckMatchStatus.INEXACT,
            _build_differences(_DIFFERENCE_COUNT),
        ),
        _build_packet("k2", 2),
    ]
    verdicts = [
        _build_verdict("k1", difference_classes=[HandCheckDifferenceClass.COSMETIC])
    ]

    with pytest.raises(HansardHandCheckError, match="has no verdict"):
        list_hand_check_flags_script.get_packet_id_to_verdict(
            packets, verdicts, list_hand_check_flags_script.SONNET_READER
        )


def test_an_earlier_flag_stays_when_this_run_does_not_flag_the_row() -> None:
    earlier_flag = _build_flag(
        "old5",
        5,
        1,
        [HandCheckFlagReason.SPEAKER_VERDICT],
        _build_verdict("old5", HandCheckSpeakerVerdict.WRONG),
        _build_verdict("old5", HandCheckSpeakerVerdict.RECORD_DOES_NOT_SAY),
    )

    union = list_hand_check_flags_script.get_union_of_flags([earlier_flag], [])

    assert union == [earlier_flag]
    assert union[0].run_number == 1
    assert union[0].packet_id == "old5"


@pytest.mark.parametrize(
    "later_reasons",
    [
        [HandCheckFlagReason.SPEAKER_VERDICT, HandCheckFlagReason.TEXT_DIFFERENCE],
        [HandCheckFlagReason.SPEAKER_VERDICT],
    ],
)
def test_a_row_flagged_in_both_runs_takes_the_union_of_the_reasons_and_the_later_record(
    later_reasons: list[HandCheckFlagReason],
) -> None:
    earlier_flag = _build_flag(
        "old5",
        5,
        1,
        [HandCheckFlagReason.TEXT_DIFFERENCE],
        _build_verdict("old5"),
        _build_verdict("old5"),
    )
    later_flag = _build_flag(
        "new5",
        5,
        2,
        later_reasons,
        _build_verdict("new5", HandCheckSpeakerVerdict.WRONG),
        None,
    )

    union = list_hand_check_flags_script.get_union_of_flags(
        [earlier_flag], [later_flag]
    )

    assert len(union) == 1
    assert union[0].reasons == [
        HandCheckFlagReason.SPEAKER_VERDICT,
        HandCheckFlagReason.TEXT_DIFFERENCE,
    ]
    assert union[0].run_number == _RERUN_NUMBER
    assert union[0].packet_id == "new5"


def test_a_run_2_sonnet_only_union_keeps_opus_round_1_verdict() -> None:
    round_1_opus_verdict = _build_verdict("old5", HandCheckSpeakerVerdict.WRONG)
    earlier_flag = _build_flag(
        "old5",
        5,
        1,
        [HandCheckFlagReason.SPEAKER_VERDICT],
        _build_verdict("old5", HandCheckSpeakerVerdict.WRONG),
        round_1_opus_verdict,
    )
    run_2_sonnet_verdict = _build_verdict("new5")
    flags = list_hand_check_flags_script.get_flags(
        [_build_packet("new5", 5, word_differences=_build_differences(1))],
        {"new5": run_2_sonnet_verdict},
        None,
        2,
    )

    union = list_hand_check_flags_script.get_union_of_flags([earlier_flag], flags)

    assert union[0].sonnet_speaker_verdict == run_2_sonnet_verdict
    assert union[0].opus_speaker_verdict == round_1_opus_verdict
    assert union[0].reasons == [
        HandCheckFlagReason.SPEAKER_VERDICT,
        HandCheckFlagReason.TEXT_DIFFERENCE,
    ]
    assert union[0].run_number == _RERUN_NUMBER


def test_a_row_new_in_run_2_has_none_for_the_reader_that_did_not_rerun() -> None:
    run_2_sonnet_verdict = _build_verdict("new6")
    flags = list_hand_check_flags_script.get_flags(
        [_build_packet("new6", 6, word_differences=_build_differences(1))],
        {"new6": run_2_sonnet_verdict},
        None,
        2,
    )

    union = list_hand_check_flags_script.get_union_of_flags([], flags)

    assert union[0].opus_speaker_verdict is None
    assert union[0].sonnet_speaker_verdict == run_2_sonnet_verdict


def test_the_union_is_sorted_by_speech_id_with_no_duplicates() -> None:
    earlier_flags = [
        _build_flag("e9", 9, 1, [HandCheckFlagReason.MATCH_STATUS], None, None),
        _build_flag("e3", 3, 1, [HandCheckFlagReason.MATCH_STATUS], None, None),
    ]
    flags = [
        _build_flag("n5", 5, 2, [HandCheckFlagReason.MATCH_STATUS], None, None),
        _build_flag("n3", 3, 2, [HandCheckFlagReason.MATCH_STATUS], None, None),
    ]

    union = list_hand_check_flags_script.get_union_of_flags(earlier_flags, flags)

    assert [flag.speech_id for flag in union] == [3, 5, 9]


@pytest.mark.parametrize(
    "kind",
    [HandCheckPlantKind.WRONG_MEMBER, HandCheckPlantKind.CREDITED_NON_SPEECH_LINE],
)
@pytest.mark.parametrize(
    ("speaker_verdict", "is_caught"),
    [
        (HandCheckSpeakerVerdict.RIGHT, False),
        (HandCheckSpeakerVerdict.WRONG, True),
        (HandCheckSpeakerVerdict.RECORD_DOES_NOT_SAY, True),
    ],
)
def test_a_plant_is_caught_by_any_speaker_verdict_but_right(
    kind: HandCheckPlantKind,
    speaker_verdict: HandCheckSpeakerVerdict,
    is_caught: bool,
) -> None:
    plant = _build_plant(101, kind)

    missed_plants = list_hand_check_flags_script.get_missed_plants(
        [plant], {101: _build_verdict("p101", speaker_verdict)}
    )

    assert (missed_plants == []) is is_caught


def test_get_missed_plants_lists_only_the_uncaught_plants_in_key_order() -> None:
    plants = [
        _build_plant(103, HandCheckPlantKind.WRONG_MEMBER),
        _build_plant(101, HandCheckPlantKind.CREDITED_NON_SPEECH_LINE),
        _build_plant(102, HandCheckPlantKind.WRONG_MEMBER),
    ]

    missed_plants = list_hand_check_flags_script.get_missed_plants(
        plants,
        {
            101: _build_verdict("p101"),
            102: _build_verdict("p102", HandCheckSpeakerVerdict.WRONG),
            103: _build_verdict("p103"),
        },
    )

    assert missed_plants == [plants[0], plants[1]]


def test_a_plant_with_no_packet_is_refused() -> None:
    with pytest.raises(HansardHandCheckError, match="has no packet"):
        list_hand_check_flags_script.get_missed_plants(
            [_build_plant(101, HandCheckPlantKind.WRONG_MEMBER)], {}
        )


def test_recall_lines_give_the_total_the_kinds_and_the_misses() -> None:
    missed_plant = _build_plant(123, HandCheckPlantKind.CREDITED_NON_SPEECH_LINE)
    plants = [
        _build_plant(121, HandCheckPlantKind.WRONG_MEMBER),
        _build_plant(122, HandCheckPlantKind.WRONG_MEMBER),
        missed_plant,
        _build_plant(124, HandCheckPlantKind.CREDITED_NON_SPEECH_LINE),
    ]

    lines = list_hand_check_flags_script.get_recall_lines(
        "Opus", plants, [missed_plant]
    )

    assert lines[0] == "Opus caught 3 of 4 planted errors"
    assert "  CREDITED_NON_SPEECH_LINE: caught 1 of 2" in lines
    assert lines[-1] == "  missed CREDITED_NON_SPEECH_LINE, speech id 123"
    assert not any(line.startswith("  recall at least") for line in lines)


def test_thirty_of_thirty_states_the_recall_bound() -> None:
    plants = [
        _build_plant(number, HandCheckPlantKind.WRONG_MEMBER) for number in range(15)
    ] + [
        _build_plant(number, HandCheckPlantKind.CREDITED_NON_SPEECH_LINE)
        for number in range(15, 30)
    ]

    lines = list_hand_check_flags_script.get_recall_lines("Sonnet", plants, [])

    assert lines[0] == "Sonnet caught 30 of 30 planted errors"
    assert lines[-1] == "  recall at least 90.5% (one-sided exact 95%)"


def test_the_missed_reader_line_names_each_reader_that_missed() -> None:
    assert (
        list_hand_check_flags_script.get_missed_reader_line(["Sonnet", "Opus"])
        == "Readers that missed a plant: Sonnet, Opus"
    )
    assert (
        list_hand_check_flags_script.get_missed_reader_line([])
        == "Readers that missed a plant: none"
    )


def test_the_summary_counts_reasons_status_gap_and_role_credits() -> None:
    office_holder = HandCheckOfficeHolder(
        office="Prime Minister",
        holder="A Holder",
        form_of_address=HandCheckFormOfAddress.MR,
        first_day=date(2000, 1, 1),
        last_day=None,
        source_url="https://example.org/source",
    )
    sampled_packets = [
        _build_packet(
            "k1",
            1,
            gap_check=HandCheckGapCheck(
                is_next_row=True, skipped_paragraphs=[], next_source_text="Next."
            ),
            role_section=HandCheckRoleSection(
                is_chair_label=True,
                office=None,
                office_holders=[],
                chair_marks=["Last mark before the row: Mr Speaker:"],
            ),
        ),
        _build_packet(
            "k2",
            2,
            HandCheckMatchStatus.INEXACT,
            gap_check=HandCheckGapCheck(
                is_next_row=False, skipped_paragraphs=[], next_source_text="Other."
            ),
            role_section=HandCheckRoleSection(
                is_chair_label=False,
                office="Prime Minister",
                office_holders=[office_holder],
                chair_marks=[],
            ),
        ),
        _build_packet(
            "k3",
            3,
            role_section=HandCheckRoleSection(
                is_chair_label=True, office=None, office_holders=[], chair_marks=[]
            ),
        ),
        _build_packet("k4", 4, HandCheckMatchStatus.NOT_FOUND),
        _build_packet("k5", 5),
    ]
    flags = [
        _build_flag(
            "k1",
            1,
            1,
            [HandCheckFlagReason.SPEAKER_VERDICT],
            _build_verdict("k1", HandCheckSpeakerVerdict.WRONG),
            _build_verdict("k1"),
        )
    ]

    lines = list_hand_check_flags_script.get_summary_lines(
        1, sampled_packets, flags, 0, None
    )

    assert "  SPEAKER_VERDICT: 1" in lines
    assert "  EXACT: 3" in lines
    assert (
        "Gap check: 1 of 2 checked rows are not followed by the next source paragraph"
        in lines
    )
    assert "Role credits (packet side): 3 rows" in lines
    assert "  chair label with a chair mark: 1" in lines
    assert "  office label with a table entry: 1" in lines
    assert "  no chair mark or table entry: 1" in lines


def test_the_summary_counts_speaker_verdicts_that_are_not_right_by_reader() -> None:
    flags = [
        _build_flag(
            "k1",
            1,
            1,
            [HandCheckFlagReason.SPEAKER_VERDICT],
            _build_verdict("k1", HandCheckSpeakerVerdict.WRONG),
            None,
        ),
        _build_flag(
            "k2",
            2,
            1,
            [HandCheckFlagReason.SPEAKER_VERDICT],
            None,
            _build_verdict("k2", HandCheckSpeakerVerdict.RECORD_DOES_NOT_SAY),
        ),
        _build_flag(
            "k3",
            3,
            1,
            [HandCheckFlagReason.SPEAKER_VERDICT],
            _build_verdict("k3"),
            _build_verdict("k3", HandCheckSpeakerVerdict.WRONG),
        ),
    ]

    lines = list_hand_check_flags_script.get_summary_lines(1, [], flags, 0, None)

    assert "  Sonnet: 1" in lines
    assert "  Opus: 2" in lines


def test_the_summary_counts_rows_in_held_reports_only_when_given_the_set() -> None:
    sampled_packets = [_build_packet("k1", 1, report_id=7), _build_packet("k2", 2)]

    held_lines = list_hand_check_flags_script.get_summary_lines(
        1, sampled_packets, [], 0, frozenset({7})
    )
    lines = list_hand_check_flags_script.get_summary_lines(
        1, sampled_packets, [], 0, None
    )

    assert "Rows in held reports: 1" in held_lines
    assert not any(line.startswith("Rows in held reports") for line in lines)


def test_a_malformed_verdict_line_is_refused_with_its_file_and_line(
    tmp_path: Path,
) -> None:
    batch_directory = tmp_path / "batch-001"
    batch_directory.mkdir()
    (batch_directory / "verdicts.jsonl").write_text(
        _build_verdict("k1").model_dump_json() + '\n{"packet_id": "k1"}\n',
        encoding="utf-8",
    )

    with pytest.raises(HansardHandCheckError) as error_info:
        list_hand_check_flags_script.get_verdicts(tmp_path)

    assert "verdicts.jsonl:2" in str(error_info.value)


def test_a_verdict_line_with_a_retired_text_key_is_refused(tmp_path: Path) -> None:
    batch_directory = tmp_path / "batch-001"
    batch_directory.mkdir()
    verdict_fields = json.loads(_build_verdict("k1").model_dump_json()) | {
        "text_verdict": "MATCHES"
    }
    (batch_directory / "verdicts.jsonl").write_text(
        json.dumps(verdict_fields) + "\n", encoding="utf-8"
    )

    with pytest.raises(HansardHandCheckError) as error_info:
        list_hand_check_flags_script.get_verdicts(tmp_path)

    assert "text_verdict" in str(error_info.value)


def test_verdicts_of_every_batch_directory_are_read(tmp_path: Path) -> None:
    first_verdict = _build_verdict("k1")
    second_verdict = _build_verdict("k2")
    _write_verdicts(tmp_path, "batch-002", [second_verdict])
    _write_verdicts(tmp_path, "batch-001", [first_verdict])

    assert list_hand_check_flags_script.get_verdicts(tmp_path) == [
        first_verdict,
        second_verdict,
    ]


def test_a_packet_with_no_verdict_is_refused() -> None:
    with pytest.raises(HansardHandCheckError, match="has no verdict"):
        list_hand_check_flags_script.get_packet_id_to_verdict(
            [_build_packet("k1", 1), _build_packet("k2", 2)],
            [_build_verdict("k1")],
            list_hand_check_flags_script.OPUS_READER,
        )


def test_a_packet_with_two_verdicts_is_refused() -> None:
    with pytest.raises(HansardHandCheckError, match="more than one verdict"):
        list_hand_check_flags_script.get_packet_id_to_verdict(
            [_build_packet("k1", 1)],
            [_build_verdict("k1"), _build_verdict("k1")],
            list_hand_check_flags_script.OPUS_READER,
        )


def test_a_verdict_for_an_unknown_packet_is_refused() -> None:
    with pytest.raises(HansardHandCheckError, match="do not exist"):
        list_hand_check_flags_script.get_packet_id_to_verdict(
            [_build_packet("k1", 1)],
            [_build_verdict("k1"), _build_verdict("k9")],
            list_hand_check_flags_script.OPUS_READER,
        )


def test_a_key_whose_digest_is_not_the_committed_one_is_refused() -> None:
    with pytest.raises(HansardHandCheckError, match="not the committed"):
        list_hand_check_flags_script.validate_can_open_plant_key(b"key", "0" * 64)


def test_a_key_whose_digest_is_the_committed_one_opens() -> None:
    assert (
        list_hand_check_flags_script.validate_can_open_plant_key(
            b"key", hashlib.sha256(b"key").hexdigest()
        )
        is None
    )


def test_the_key_is_not_opened_while_a_verdict_is_missing(tmp_path: Path) -> None:
    packets = [_build_packet("k1", 1), _build_packet("k2", 2)]

    with pytest.raises(HansardHandCheckError, match="has no verdict"):
        _list_flags(
            tmp_path,
            packets,
            [_build_verdict("k1")],
            _build_right_verdicts(packets),
            plant_key_paths=list_hand_check_flags_script.PlantKeyPaths(
                tmp_path / "missing-key.json", tmp_path / "missing-key.sha256"
            ),
        )
    _assert_no_output_written(tmp_path, 1)


def test_the_key_is_not_opened_while_a_class_count_is_wrong(tmp_path: Path) -> None:
    packets = [
        _build_packet(
            "k1",
            1,
            HandCheckMatchStatus.INEXACT,
            _build_differences(_DIFFERENCE_COUNT),
        )
    ]

    with pytest.raises(
        HansardHandCheckError, match="wrong number of difference classes"
    ):
        _list_flags(
            tmp_path,
            packets,
            [
                _build_verdict(
                    "k1", difference_classes=[HandCheckDifferenceClass.COSMETIC]
                )
            ],
            _build_right_verdicts(packets),
            plant_key_paths=list_hand_check_flags_script.PlantKeyPaths(
                tmp_path / "missing-key.json", tmp_path / "missing-key.sha256"
            ),
        )
    _assert_no_output_written(tmp_path, 1)


def test_a_key_that_differs_from_its_committed_hash_stops_the_run_and_writes_nothing(
    tmp_path: Path,
) -> None:
    packets = [_build_packet("k1", 101)]
    plant_key_paths = _write_key(
        tmp_path, 1, [_build_plant(101, HandCheckPlantKind.WRONG_MEMBER)]
    )
    plant_key_paths.hash_path.write_text("0" * 64 + "\n", encoding="utf-8")

    with pytest.raises(HansardHandCheckError, match="not the committed"):
        _list_flags(
            tmp_path,
            packets,
            _build_right_verdicts(packets),
            _build_right_verdicts(packets),
            plant_key_paths=plant_key_paths,
        )
    _assert_no_output_written(tmp_path, 1)


@pytest.mark.parametrize(
    ("is_sonnet_given", "is_opus_given"), [(False, True), (True, False)]
)
def test_run_1_refuses_a_missing_reader(
    tmp_path: Path, is_sonnet_given: bool, is_opus_given: bool
) -> None:
    packets = [_build_packet("k1", 1)]

    with pytest.raises(HansardHandCheckError, match="Run 1 needs both readers"):
        _list_flags(
            tmp_path,
            packets,
            _build_right_verdicts(packets) if is_sonnet_given else None,
            _build_right_verdicts(packets) if is_opus_given else None,
        )
    _assert_no_output_written(tmp_path, 1)


def test_a_third_run_is_refused(tmp_path: Path) -> None:
    packets = [_build_packet("k1", 1)]
    earlier_flags_path = tmp_path / "flags-run-2.json"
    earlier_flags_path.write_text(
        HandCheckFlags([]).model_dump_json(), encoding="utf-8"
    )

    with pytest.raises(HansardHandCheckError, match="allows one rerun"):
        _list_flags(
            tmp_path,
            packets,
            _build_right_verdicts(packets),
            None,
            run_number=3,
            earlier_flags_path=earlier_flags_path,
        )
    _assert_no_output_written(tmp_path, 3)


def test_a_later_run_with_no_reader_is_refused(tmp_path: Path) -> None:
    earlier_flags_path = tmp_path / "flags-run-1.json"
    earlier_flags_path.write_text(
        HandCheckFlags([]).model_dump_json(), encoding="utf-8"
    )

    with pytest.raises(HansardHandCheckError, match="at least one reader"):
        _list_flags(
            tmp_path,
            [_build_packet("k1", 1)],
            None,
            None,
            run_number=2,
            earlier_flags_path=earlier_flags_path,
        )
    _assert_no_output_written(tmp_path, 2)


def test_a_run_without_a_key_flags_every_reasoned_row_and_scores_nothing(
    tmp_path: Path,
) -> None:
    packets = [_build_packet("s1", 1), _build_packet("s2", 2), _build_packet("s3", 3)]

    output_paths = _list_flags(
        tmp_path,
        packets,
        [
            _build_verdict("s1"),
            _build_verdict("s2", HandCheckSpeakerVerdict.WRONG),
            _build_verdict("s3"),
        ],
        _build_right_verdicts(packets),
    )

    assert [flag.packet_id for flag in _get_written_flags(output_paths.flags_path)] == [
        "s2"
    ]
    summary_lines = _get_summary_lines(output_paths.summary_path)
    assert "Flags: 1, of which 0 kept from an earlier run" in summary_lines
    assert not any("planted errors" in line for line in summary_lines)


def test_a_run_with_a_key_scores_both_readers_and_leaves_the_plants_out_of_the_flags(
    tmp_path: Path,
) -> None:
    packets = [
        _build_packet("s1", 1),
        _build_packet("s2", 2, HandCheckMatchStatus.INEXACT),
        _build_packet("p101", 101),
        _build_packet("p102", 102),
    ]
    plant_key_paths = _write_key(
        tmp_path,
        1,
        [
            _build_plant(101, HandCheckPlantKind.WRONG_MEMBER),
            _build_plant(102, HandCheckPlantKind.CREDITED_NON_SPEECH_LINE),
        ],
    )

    output_paths = _list_flags(
        tmp_path,
        packets,
        [
            _build_verdict("s1"),
            _build_verdict("s2"),
            _build_verdict("p101", HandCheckSpeakerVerdict.WRONG),
            _build_verdict("p102", HandCheckSpeakerVerdict.WRONG),
        ],
        [
            _build_verdict("s1"),
            _build_verdict("s2"),
            _build_verdict("p101", HandCheckSpeakerVerdict.WRONG),
            _build_verdict("p102"),
        ],
        plant_key_paths=plant_key_paths,
    )

    assert [flag.packet_id for flag in _get_written_flags(output_paths.flags_path)] == [
        "s2"
    ]
    summary_lines = _get_summary_lines(output_paths.summary_path)
    assert "Sonnet caught 2 of 2 planted errors" in summary_lines
    assert "Opus caught 1 of 2 planted errors" in summary_lines
    assert "  missed CREDITED_NON_SPEECH_LINE, speech id 102" in summary_lines
    assert "Readers that missed a plant: Opus" in summary_lines
    assert "Sampled rows: 2" in summary_lines


def test_the_flag_list_reads_back_as_the_next_runs_earlier_list(
    tmp_path: Path,
) -> None:
    run_1_packets = [
        _build_packet("s1", 1),
        _build_packet("s2", 2, HandCheckMatchStatus.INEXACT),
    ]
    run_1_sonnet_verdict = _build_verdict("s2", HandCheckSpeakerVerdict.WRONG)
    run_1_opus_verdict = _build_verdict("s2")
    run_1_paths = _list_flags(
        tmp_path,
        run_1_packets,
        [_build_verdict("s1"), run_1_sonnet_verdict],
        [_build_verdict("s1"), run_1_opus_verdict],
    )
    run_2_packets = [_build_packet("t1", 1), _build_packet("t2", 2)]

    run_2_paths = _list_flags(
        tmp_path,
        run_2_packets,
        _build_right_verdicts(run_2_packets),
        None,
        run_number=2,
        earlier_flags_path=run_1_paths.flags_path,
    )

    written_flags = _get_written_flags(run_2_paths.flags_path)
    assert [flag.speech_id for flag in written_flags] == [2]
    assert written_flags[0].run_number == 1
    assert written_flags[0].packet_id == "s2"
    assert written_flags[0].sonnet_speaker_verdict == run_1_sonnet_verdict
    assert written_flags[0].opus_speaker_verdict == run_1_opus_verdict
    assert "Flags: 1, of which 1 kept from an earlier run" in _get_summary_lines(
        run_2_paths.summary_path
    )


def test_a_run_2_with_one_reader_validates_and_scores_only_that_reader(
    tmp_path: Path,
) -> None:
    run_1_packets = [
        _build_packet("s1", 1),
        _build_packet("s2", 2, HandCheckMatchStatus.INEXACT),
        _build_packet("s3", 3),
        _build_packet("p101", 101),
        _build_packet("p102", 102),
    ]
    run_1_opus_verdict = _build_verdict("s2")
    run_1_paths = _list_flags(
        tmp_path,
        run_1_packets,
        [
            _build_verdict("s1"),
            _build_verdict("s2"),
            _build_verdict("s3"),
            _build_verdict("p101", HandCheckSpeakerVerdict.WRONG),
            _build_verdict("p102"),
        ],
        [
            _build_verdict("s1"),
            run_1_opus_verdict,
            _build_verdict("s3"),
            _build_verdict("p101", HandCheckSpeakerVerdict.WRONG),
            _build_verdict("p102", HandCheckSpeakerVerdict.WRONG),
        ],
        plant_key_paths=_write_key(
            tmp_path,
            1,
            [
                _build_plant(101, HandCheckPlantKind.WRONG_MEMBER),
                _build_plant(102, HandCheckPlantKind.CREDITED_NON_SPEECH_LINE),
            ],
        ),
    )
    run_2_packets = [
        _build_packet("t1", 1),
        _build_packet("t2", 2),
        _build_packet("t3", 3, HandCheckMatchStatus.NOT_FOUND),
        _build_packet("p201", 201),
        _build_packet("p202", 202),
    ]

    run_2_paths = _list_flags(
        tmp_path,
        run_2_packets,
        [
            _build_verdict("t1"),
            _build_verdict("t2"),
            _build_verdict("t3"),
            _build_verdict("p201", HandCheckSpeakerVerdict.WRONG),
            _build_verdict("p202", HandCheckSpeakerVerdict.RECORD_DOES_NOT_SAY),
        ],
        None,
        run_number=2,
        earlier_flags_path=run_1_paths.flags_path,
        plant_key_paths=_write_key(
            tmp_path,
            2,
            [
                _build_plant(201, HandCheckPlantKind.WRONG_MEMBER),
                _build_plant(202, HandCheckPlantKind.CREDITED_NON_SPEECH_LINE),
            ],
        ),
    )

    assert not (tmp_path / "opus-run-2").exists()
    summary_lines = _get_summary_lines(run_2_paths.summary_path)
    assert "Sonnet caught 2 of 2 planted errors" in summary_lines
    assert not any("Opus caught" in line for line in summary_lines)
    speech_id_to_flag = {
        flag.speech_id: flag for flag in _get_written_flags(run_2_paths.flags_path)
    }
    assert sorted(speech_id_to_flag) == [2, 3]
    assert speech_id_to_flag[3].opus_speaker_verdict is None
    assert speech_id_to_flag[2].opus_speaker_verdict == run_1_opus_verdict


def test_a_later_run_without_the_earlier_flag_list_is_refused(
    tmp_path: Path,
) -> None:
    packets = [_build_packet("k1", 1)]

    with pytest.raises(HansardHandCheckError, match="needs the flag list"):
        _list_flags(
            tmp_path,
            packets,
            _build_right_verdicts(packets),
            _build_right_verdicts(packets),
            run_number=2,
        )
    _assert_no_output_written(tmp_path, 2)


def test_an_existing_flag_list_is_not_overwritten(tmp_path: Path) -> None:
    packets = [_build_packet("k1", 1, HandCheckMatchStatus.INEXACT)]
    flags_path = tmp_path / "flags-run-1.json"
    flags_path.write_text("run 1 list", encoding="utf-8")

    with pytest.raises(FileExistsError):
        _list_flags(
            tmp_path,
            packets,
            _build_right_verdicts(packets),
            _build_right_verdicts(packets),
        )
    assert flags_path.read_text(encoding="utf-8") == "run 1 list"
    assert not (tmp_path / "summary-run-1.txt").exists()


def test_a_held_reports_file_adds_the_held_row_count(tmp_path: Path) -> None:
    packets = [_build_packet("k1", 1, report_id=7)]
    held_reports_path = tmp_path / "held.json"
    held_reports_path.write_text('[{"report_id": 7, "reason": "x"}]', encoding="utf-8")

    output_paths = _list_flags(
        tmp_path,
        packets,
        _build_right_verdicts(packets),
        _build_right_verdicts(packets),
        held_reports_path=held_reports_path,
    )

    assert "Rows in held reports: 1" in _get_summary_lines(output_paths.summary_path)
