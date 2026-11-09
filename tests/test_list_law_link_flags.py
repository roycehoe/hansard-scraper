import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

import scripts.list_law_link_flags as list_law_link_flags_script
from enums import LawLinkCheckRule, LawLinkVerdict
from exceptions import HansardLawLinkCheckError
from schemas.law_link_check_flag import LawLinkCheckFlag, LawLinkCheckFlags
from schemas.law_link_check_packet import LawLinkCheckPacket, LawLinkCheckPackets
from schemas.law_link_check_plant_key import LawLinkCheckPlant, LawLinkCheckPlantKey
from schemas.law_link_check_verdict import LawLinkCheckVerdict
from scripts.list_law_link_flags import get_verdicts, list_law_link_flags

_PLANT_PACKET_ID = "plant"
_RECALL_PLANT_COUNT = 45
_SOURCE_TEXT = "Source text"
_DATA_SAYS = "Data says"
_RULE_TEXT = "Rule text"
_MEMBER_ROW_ID = 9
_EARLIER_MEMBER_ROW_ID = 2
_STAGE_ROW_ID = 5
_LINK_FIELD_BILL_ID = 7


@dataclass(frozen=True)
class _KeyPaths:
    key_path: Path
    hash_path: Path


@dataclass(frozen=True)
class _OutputPaths:
    flags_path: Path
    summary_path: Path


def _build_packet(
    packet_id: str,
    rule: LawLinkCheckRule = LawLinkCheckRule.MEMBER,
    row_id: int = 1,
) -> LawLinkCheckPacket:
    return LawLinkCheckPacket(
        packet_id=packet_id,
        rule=rule,
        group="1960s bill",
        row_id=row_id,
        source_text=_SOURCE_TEXT,
        data_says=_DATA_SAYS,
        rule_text=_RULE_TEXT,
    )


def _build_verdict(
    packet_id: str, verdict: LawLinkVerdict = LawLinkVerdict.RIGHT
) -> LawLinkCheckVerdict:
    return LawLinkCheckVerdict(packet_id=packet_id, verdict=verdict, note="Note.")


def _build_plant(
    packet_id: str, rule: LawLinkCheckRule = LawLinkCheckRule.MEMBER
) -> LawLinkCheckPlant:
    return LawLinkCheckPlant(
        packet_id=packet_id, rule=rule, original="original", planted="planted"
    )


def _write_verdicts(
    directory: Path, batch_name: str, verdicts: list[LawLinkCheckVerdict]
) -> None:
    batch_directory = directory / batch_name
    batch_directory.mkdir(parents=True, exist_ok=True)
    (batch_directory / "verdicts.jsonl").write_text(
        "".join(f"{verdict.model_dump_json()}\n" for verdict in verdicts),
        encoding="utf-8",
    )


def _write_key(tmp_path: Path, plants: list[LawLinkCheckPlant]) -> _KeyPaths:
    key_path = tmp_path / "key.json"
    hash_path = tmp_path / "key.sha256"
    key_bytes = LawLinkCheckPlantKey(plants=plants).model_dump_json().encode("utf-8")
    key_path.write_bytes(key_bytes)
    hash_path.write_text(hashlib.sha256(key_bytes).hexdigest() + "\n", encoding="utf-8")
    return _KeyPaths(key_path, hash_path)


def _list_flags(
    tmp_path: Path,
    packets: list[LawLinkCheckPacket],
    sonnet_verdicts: list[LawLinkCheckVerdict],
    opus_verdicts: list[LawLinkCheckVerdict],
    plants: Optional[list[LawLinkCheckPlant]] = None,
    key_paths: Optional[_KeyPaths] = None,
) -> _OutputPaths:
    if plants is None:
        plants = [_build_plant(_PLANT_PACKET_ID)]
        packets = [*packets, _build_packet(_PLANT_PACKET_ID)]
        sonnet_verdicts = [
            *sonnet_verdicts,
            _build_verdict(_PLANT_PACKET_ID, LawLinkVerdict.WRONG),
        ]
        opus_verdicts = [
            *opus_verdicts,
            _build_verdict(_PLANT_PACKET_ID, LawLinkVerdict.WRONG),
        ]
    packets_path = tmp_path / "packets.json"
    packets_path.write_text(
        LawLinkCheckPackets(packets).model_dump_json(), encoding="utf-8"
    )
    _write_verdicts(tmp_path / "sonnet", "batch-001", sonnet_verdicts)
    _write_verdicts(tmp_path / "opus", "batch-001", opus_verdicts)
    if key_paths is None:
        key_paths = _write_key(tmp_path, plants)
    output_paths = _OutputPaths(tmp_path / "flags.json", tmp_path / "summary.txt")
    list_law_link_flags(
        packets_path,
        tmp_path / "sonnet",
        tmp_path / "opus",
        key_paths.key_path,
        key_paths.hash_path,
        output_paths.flags_path,
        output_paths.summary_path,
    )
    return output_paths


def _get_written_flags(flags_path: Path) -> list[LawLinkCheckFlag]:
    return LawLinkCheckFlags.model_validate_json(
        flags_path.read_text(encoding="utf-8")
    ).root


def _get_summary_lines(summary_path: Path) -> list[str]:
    return summary_path.read_text(encoding="utf-8").splitlines()


def test_a_row_both_readers_call_right_has_no_flag(tmp_path: Path) -> None:
    output_paths = _list_flags(
        tmp_path, [_build_packet("a")], [_build_verdict("a")], [_build_verdict("a")]
    )

    assert _get_written_flags(output_paths.flags_path) == []


@pytest.mark.parametrize("is_sonnet_reader", [True, False])
@pytest.mark.parametrize(
    "verdict", [LawLinkVerdict.WRONG, LawLinkVerdict.RECORD_DOES_NOT_SAY]
)
def test_either_readers_verdict_that_is_not_right_flags_the_row(
    tmp_path: Path, is_sonnet_reader: bool, verdict: LawLinkVerdict
) -> None:
    objecting_verdicts = [_build_verdict("a", verdict)]
    agreeing_verdicts = [_build_verdict("a")]

    output_paths = _list_flags(
        tmp_path,
        [_build_packet("a")],
        objecting_verdicts if is_sonnet_reader else agreeing_verdicts,
        agreeing_verdicts if is_sonnet_reader else objecting_verdicts,
    )

    (flag,) = _get_written_flags(output_paths.flags_path)
    assert flag.packet_id == "a"
    assert flag.source_text == _SOURCE_TEXT
    assert flag.data_says == _DATA_SAYS
    assert flag.rule_text == _RULE_TEXT
    assert flag.sonnet_verdict.verdict == (
        verdict if is_sonnet_reader else LawLinkVerdict.RIGHT
    )
    assert flag.opus_verdict.verdict == (
        LawLinkVerdict.RIGHT if is_sonnet_reader else verdict
    )


def test_two_readers_that_both_object_give_one_flag(tmp_path: Path) -> None:
    output_paths = _list_flags(
        tmp_path,
        [_build_packet("a")],
        [_build_verdict("a", LawLinkVerdict.WRONG)],
        [_build_verdict("a", LawLinkVerdict.RECORD_DOES_NOT_SAY)],
    )

    assert len(_get_written_flags(output_paths.flags_path)) == 1


def test_flags_are_ordered_by_rule_then_row_id(tmp_path: Path) -> None:
    packets = [
        _build_packet("stage", LawLinkCheckRule.STAGE_FIRST_READING, _STAGE_ROW_ID),
        _build_packet("late", LawLinkCheckRule.MEMBER, _MEMBER_ROW_ID),
        _build_packet("early", LawLinkCheckRule.MEMBER, _EARLIER_MEMBER_ROW_ID),
    ]
    wrong_verdicts = [
        _build_verdict(packet.packet_id, LawLinkVerdict.WRONG) for packet in packets
    ]

    output_paths = _list_flags(tmp_path, packets, wrong_verdicts, wrong_verdicts)

    assert [flag.packet_id for flag in _get_written_flags(output_paths.flags_path)] == [
        "early",
        "late",
        "stage",
    ]


def test_a_planted_packet_is_scored_and_never_flagged(tmp_path: Path) -> None:
    output_paths = _list_flags(
        tmp_path, [_build_packet("a")], [_build_verdict("a")], [_build_verdict("a")]
    )

    assert _get_written_flags(output_paths.flags_path) == []
    summary_lines = _get_summary_lines(output_paths.summary_path)
    assert "Sonnet caught 1 of 1 planted errors" in summary_lines
    assert "Opus caught 1 of 1 planted errors" in summary_lines


def test_a_reader_that_calls_a_plant_right_is_listed_as_missing_it(
    tmp_path: Path,
) -> None:
    output_paths = _list_flags(
        tmp_path,
        [_build_packet(_PLANT_PACKET_ID)],
        [_build_verdict(_PLANT_PACKET_ID, LawLinkVerdict.RIGHT)],
        [_build_verdict(_PLANT_PACKET_ID, LawLinkVerdict.WRONG)],
        plants=[_build_plant(_PLANT_PACKET_ID)],
    )

    summary_lines = _get_summary_lines(output_paths.summary_path)
    assert f"  missed MEMBER, packet {_PLANT_PACKET_ID}" in summary_lines
    assert "Readers that missed a plant: Sonnet" in summary_lines


def test_a_reader_that_catches_every_plant_gets_the_recall_bound(
    tmp_path: Path,
) -> None:
    plant_packet_ids = [f"plant-{index}" for index in range(_RECALL_PLANT_COUNT)]
    wrong_verdicts = [
        _build_verdict(packet_id, LawLinkVerdict.WRONG)
        for packet_id in plant_packet_ids
    ]

    output_paths = _list_flags(
        tmp_path,
        [_build_packet(packet_id) for packet_id in plant_packet_ids],
        wrong_verdicts,
        wrong_verdicts,
        plants=[_build_plant(packet_id) for packet_id in plant_packet_ids],
    )

    expected_line = f"  recall at least {0.05 ** (1 / _RECALL_PLANT_COUNT):.1%} (one-sided exact 95%)"
    summary_lines = _get_summary_lines(output_paths.summary_path)
    assert summary_lines.count(expected_line) == len(["Sonnet", "Opus"])
    assert "Readers that missed a plant: none" in summary_lines


def test_a_key_that_does_not_match_its_hash_is_refused_and_writes_nothing(
    tmp_path: Path,
) -> None:
    key_paths = _write_key(tmp_path, [_build_plant(_PLANT_PACKET_ID)])
    key_paths.hash_path.write_text("0" * 64 + "\n", encoding="utf-8")

    with pytest.raises(HansardLawLinkCheckError, match="hashes to"):
        _list_flags(
            tmp_path,
            [_build_packet(_PLANT_PACKET_ID)],
            [_build_verdict(_PLANT_PACKET_ID)],
            [_build_verdict(_PLANT_PACKET_ID)],
            plants=[],
            key_paths=key_paths,
        )

    assert not (tmp_path / "flags.json").exists()
    assert not (tmp_path / "summary.txt").exists()


def test_a_key_with_no_plant_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HansardLawLinkCheckError, match="holds no plant to score"):
        _list_flags(
            tmp_path,
            [_build_packet("a")],
            [_build_verdict("a")],
            [_build_verdict("a")],
            plants=[],
        )


def test_a_plant_with_no_packet_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HansardLawLinkCheckError, match="has no packet"):
        _list_flags(
            tmp_path,
            [_build_packet("a")],
            [_build_verdict("a")],
            [_build_verdict("a")],
            plants=[_build_plant("ghost")],
        )


def test_a_missing_verdict_is_refused(tmp_path: Path) -> None:
    with pytest.raises(
        HansardLawLinkCheckError, match="Sonnet has no verdict for 1 packets"
    ):
        _list_flags(
            tmp_path,
            [_build_packet("a"), _build_packet("b")],
            [_build_verdict("a")],
            [_build_verdict("a"), _build_verdict("b")],
        )


def test_a_repeated_verdict_is_refused(tmp_path: Path) -> None:
    with pytest.raises(
        HansardLawLinkCheckError, match="Opus wrote more than one verdict for 1 packets"
    ):
        _list_flags(
            tmp_path,
            [_build_packet("a")],
            [_build_verdict("a")],
            [_build_verdict("a"), _build_verdict("a")],
        )


def test_a_verdict_for_an_unknown_packet_is_refused(tmp_path: Path) -> None:
    with pytest.raises(
        HansardLawLinkCheckError,
        match="Sonnet wrote verdicts for 1 packets that do not exist",
    ):
        _list_flags(
            tmp_path,
            [_build_packet("a")],
            [_build_verdict("a"), _build_verdict("ghost")],
            [_build_verdict("a")],
        )


def test_a_verdict_line_with_a_link_field_is_refused(tmp_path: Path) -> None:
    verdict_line = _build_verdict("a").model_dump_json()
    batch_directory = tmp_path / "batch-001"
    batch_directory.mkdir()
    (batch_directory / "verdicts.jsonl").write_text(
        verdict_line[:-1] + f', "bill_id": {_LINK_FIELD_BILL_ID}}}\n', encoding="utf-8"
    )

    with pytest.raises(HansardLawLinkCheckError, match="is not a valid verdict line"):
        get_verdicts(tmp_path)

    assert set(LawLinkCheckVerdict.model_fields) == {"packet_id", "verdict", "note"}


def test_an_existing_flags_file_is_not_overwritten(tmp_path: Path) -> None:
    packets = [_build_packet("a")]
    verdicts = [_build_verdict("a", LawLinkVerdict.WRONG)]
    output_paths = _list_flags(tmp_path, packets, verdicts, verdicts)
    first_flags_text = output_paths.flags_path.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        _list_flags(tmp_path, packets, verdicts, verdicts)

    assert output_paths.flags_path.read_text(encoding="utf-8") == first_flags_text


def test_the_summary_counts_flags_by_rule_and_by_reader(tmp_path: Path) -> None:
    packets = [
        _build_packet("member-flagged", LawLinkCheckRule.MEMBER),
        _build_packet("member-clean", LawLinkCheckRule.MEMBER),
        _build_packet("stage-flagged", LawLinkCheckRule.STAGE_FIRST_READING),
    ]
    sonnet_verdicts = [
        _build_verdict("member-flagged", LawLinkVerdict.WRONG),
        _build_verdict("member-clean"),
        _build_verdict("stage-flagged", LawLinkVerdict.WRONG),
    ]
    opus_verdicts = [
        _build_verdict("member-flagged"),
        _build_verdict("member-clean"),
        _build_verdict("stage-flagged", LawLinkVerdict.RECORD_DOES_NOT_SAY),
    ]

    output_paths = _list_flags(tmp_path, packets, sonnet_verdicts, opus_verdicts)

    summary_lines = _get_summary_lines(output_paths.summary_path)
    assert "Sampled rows: 3" in summary_lines
    assert "Flags: 2" in summary_lines
    assert "  MEMBER: 1 of 2" in summary_lines
    assert "  STAGE_FIRST_READING: 1 of 1" in summary_lines
    assert "  Sonnet: 2" in summary_lines
    assert "  Opus: 1" in summary_lines


def test_the_flag_script_opens_no_database() -> None:
    script_text = Path(list_law_link_flags_script.__file__).read_text(encoding="utf-8")

    assert "database" not in script_text
    assert "Session" not in script_text
    assert "validate_can_write" not in script_text
