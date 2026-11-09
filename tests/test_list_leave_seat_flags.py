import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from enums import LeaveSeatCheckVerdict
from exceptions import HansardHandCheckError
from schemas.leave_seat_check import (
    LeaveSeatCheckFlag,
    LeaveSeatCheckKeyEntry,
    LeaveSeatCheckPacket,
)
from scripts.list_leave_seat_flags import list_leave_seat_flags

_RIGHT = LeaveSeatCheckVerdict.RIGHT
_WRONG = LeaveSeatCheckVerdict.WRONG
_UNSURE = LeaveSeatCheckVerdict.UNSURE
_FORMAT_GROUP = "format|STRUCTURED_LIST|2020"
_ORDER_BREAK_GROUP = "year_order_break"
_FLAGS_ADAPTER = TypeAdapter(list[LeaveSeatCheckFlag])
_KEY_ADAPTER = TypeAdapter(list[LeaveSeatCheckKeyEntry])


@dataclass(frozen=True)
class _Case:
    packets_path: Path
    sonnet_directory: Path
    opus_directory: Path
    key_path: Path
    key_hash_path: Path
    output_path: Path
    summary_path: Path


def _write_verdicts(
    directory: Path, packet_id_to_verdict: dict[str, LeaveSeatCheckVerdict]
) -> None:
    directory.mkdir()
    (directory / "verdicts.jsonl").write_text(
        "".join(
            json.dumps({"packet_id": packet_id, "verdict": verdict, "note": "n"}) + "\n"
            for packet_id, verdict in packet_id_to_verdict.items()
        ),
        encoding="utf-8",
    )


def _build_case(
    tmp_path: Path,
    packets: list[tuple[str, str, bool]],
    sonnet: dict[str, LeaveSeatCheckVerdict],
    opus: dict[str, LeaveSeatCheckVerdict],
) -> _Case:
    case = _Case(
        packets_path=tmp_path / "packets.jsonl",
        sonnet_directory=tmp_path / "sonnet",
        opus_directory=tmp_path / "opus",
        key_path=tmp_path / "key.json",
        key_hash_path=tmp_path / "key.sha256",
        output_path=tmp_path / "flags.json",
        summary_path=tmp_path / "summary.txt",
    )
    case.packets_path.write_text(
        "".join(
            LeaveSeatCheckPacket(
                packet_id=packet_id, source_text="s", data_says="d", rule="r"
            ).model_dump_json()
            + "\n"
            for packet_id, _, _ in packets
        ),
        encoding="utf-8",
    )
    key_bytes = _KEY_ADAPTER.dump_json(
        [
            LeaveSeatCheckKeyEntry(
                packet_id=packet_id,
                group=group,
                table_name="leave_period_printing",
                row_id=index,
                is_plant=is_plant,
                plant_note="moved" if is_plant else None,
            )
            for index, (packet_id, group, is_plant) in enumerate(packets, 1)
        ],
        indent=2,
    )
    case.key_path.write_bytes(key_bytes)
    case.key_hash_path.write_text(
        hashlib.sha256(key_bytes).hexdigest() + "\n", encoding="utf-8"
    )
    _write_verdicts(case.sonnet_directory, sonnet)
    _write_verdicts(case.opus_directory, opus)
    return case


def _run(case: _Case) -> None:
    list_leave_seat_flags(
        case.packets_path,
        case.sonnet_directory,
        case.opus_directory,
        case.key_path,
        case.key_hash_path,
        case.output_path,
        case.summary_path,
    )


def _get_flagged_packet_ids(case: _Case) -> list[str]:
    return [
        flag.packet_id
        for flag in _FLAGS_ADAPTER.validate_json(case.output_path.read_bytes())
    ]


def test_a_row_both_readers_call_right_is_not_flagged(tmp_path: Path) -> None:
    case = _build_case(
        tmp_path, [("p1", _FORMAT_GROUP, False)], {"p1": _RIGHT}, {"p1": _RIGHT}
    )

    _run(case)

    assert _get_flagged_packet_ids(case) == []


@pytest.mark.parametrize(
    ("sonnet_verdict", "opus_verdict"),
    [(_WRONG, _RIGHT), (_UNSURE, _RIGHT), (_RIGHT, _WRONG), (_RIGHT, _UNSURE)],
)
def test_a_wrong_or_unsure_verdict_from_either_reader_flags_the_row(
    tmp_path: Path,
    sonnet_verdict: LeaveSeatCheckVerdict,
    opus_verdict: LeaveSeatCheckVerdict,
) -> None:
    case = _build_case(
        tmp_path,
        [("p1", _FORMAT_GROUP, False)],
        {"p1": sonnet_verdict},
        {"p1": opus_verdict},
    )

    _run(case)

    flags = _FLAGS_ADAPTER.validate_json(case.output_path.read_bytes())
    assert [(flag.packet_id, flag.group, flag.row_id) for flag in flags] == [
        ("p1", _FORMAT_GROUP, 1)
    ]
    assert (flags[0].sonnet_verdict, flags[0].opus_verdict) == (
        sonnet_verdict,
        opus_verdict,
    )


def test_a_year_order_break_row_is_flagged_with_two_right_verdicts(
    tmp_path: Path,
) -> None:
    case = _build_case(
        tmp_path, [("p1", _ORDER_BREAK_GROUP, False)], {"p1": _RIGHT}, {"p1": _RIGHT}
    )

    _run(case)

    assert _get_flagged_packet_ids(case) == ["p1"]


def test_a_plant_is_scored_and_left_out_of_the_flags(tmp_path: Path) -> None:
    case = _build_case(
        tmp_path,
        [("p1", _FORMAT_GROUP, False), ("p2", _FORMAT_GROUP, True)],
        {"p1": _RIGHT, "p2": _WRONG},
        {"p1": _RIGHT, "p2": _RIGHT},
    )

    _run(case)

    assert _get_flagged_packet_ids(case) == []
    assert case.summary_path.read_text(encoding="utf-8").splitlines() == [
        "group\tsample\tplants\tsonnet_plants_caught\topus_plants_caught\tflagged",
        f"{_FORMAT_GROUP}\t1\t1\t1\t0\t0",
    ]


def test_a_short_verdict_file_refuses(tmp_path: Path) -> None:
    case = _build_case(
        tmp_path,
        [("p1", _FORMAT_GROUP, False), ("p2", _FORMAT_GROUP, False)],
        {"p1": _RIGHT},
        {"p1": _RIGHT, "p2": _RIGHT},
    )

    with pytest.raises(HansardHandCheckError, match="lack exactly one Sonnet"):
        _run(case)

    assert not case.output_path.exists()


def test_a_second_verdict_line_for_a_packet_refuses(tmp_path: Path) -> None:
    case = _build_case(
        tmp_path, [("p1", _FORMAT_GROUP, False)], {"p1": _RIGHT}, {"p1": _RIGHT}
    )
    with (case.opus_directory / "verdicts.jsonl").open("a", encoding="utf-8") as file:
        file.write(
            json.dumps({"packet_id": "p1", "verdict": "WRONG", "note": "n"}) + "\n"
        )

    with pytest.raises(HansardHandCheckError, match="lack exactly one Opus"):
        _run(case)


def test_a_wrong_key_hash_refuses(tmp_path: Path) -> None:
    case = _build_case(
        tmp_path, [("p1", _FORMAT_GROUP, False)], {"p1": _RIGHT}, {"p1": _RIGHT}
    )
    case.key_hash_path.write_text("0" * 64 + "\n", encoding="utf-8")

    with pytest.raises(HansardHandCheckError, match="not the committed"):
        _run(case)

    assert not case.output_path.exists()


def test_an_existing_output_refuses(tmp_path: Path) -> None:
    case = _build_case(
        tmp_path, [("p1", _FORMAT_GROUP, False)], {"p1": _RIGHT}, {"p1": _RIGHT}
    )
    case.output_path.write_text("[]", encoding="utf-8")

    with pytest.raises(HansardHandCheckError, match="already exists"):
        _run(case)

    assert case.output_path.read_text(encoding="utf-8") == "[]"
