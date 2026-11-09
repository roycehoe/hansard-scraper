import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

import scripts.list_report_link_flags as list_report_link_flags_script
from enums import (
    ReportLinkPlantKind,
    ReportLinkRule,
    ReportLinkType,
    ReportLinkVerdict,
)
from exceptions import HansardReportLinkCheckError
from schemas.report_link_check import (
    ReportLinkCheckFlags,
    ReportLinkCheckKey,
    ReportLinkCheckPacket,
    ReportLinkCheckPackets,
    ReportLinkCheckPlant,
    ReportLinkCheckReportText,
)
from scripts.list_report_link_flags import list_report_link_flags

_REAL_PACKET_IDS = ("real-1", "real-2")
_PLANT_PACKET_IDS = ("plant-1", "plant-2")
_SITTING_DATE = date(2020, 3, 3)


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _build_report_text(title: str) -> ReportLinkCheckReportText:
    return ReportLinkCheckReportText(
        title=title, sitting_date=_SITTING_DATE, opening_text="Opening."
    )


def _build_packet(packet_id: str) -> ReportLinkCheckPacket:
    return ReportLinkCheckPacket(
        packet_id=packet_id,
        group="reply",
        rule=ReportLinkRule.PRINTED_TITLE_ON_PRINTED_DATE,
        link_type=ReportLinkType.REPLY,
        source_report_id=f"source-{packet_id}",
        target_report_id=f"target-{packet_id}",
        printed_citation=f"citation {packet_id}",
        paragraph=f"[Please refer to citation {packet_id}]",
        source_report=_build_report_text("Source"),
        target_report=_build_report_text(f"Target {packet_id}"),
        same_title_reports=[],
    )


def _write_verdicts(
    verdicts_directory: Path, packet_id_to_verdict: dict[str, ReportLinkVerdict]
) -> None:
    batch_directory = verdicts_directory / "batch-01"
    batch_directory.mkdir(parents=True)
    (batch_directory / "verdicts.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "packet_id": packet_id,
                    "verdict": verdict,
                    "note": f"note {packet_id}",
                }
            )
            + "\n"
            for packet_id, verdict in packet_id_to_verdict.items()
        ),
        encoding="utf-8",
    )


def _get_all_right() -> dict[str, ReportLinkVerdict]:
    return {
        packet_id: ReportLinkVerdict.RIGHT
        for packet_id in (*_REAL_PACKET_IDS, *_PLANT_PACKET_IDS)
    }


class _Inputs:
    def __init__(self, tmp_path: Path) -> None:
        self.packets_path = tmp_path / "packets.json"
        self.key_path = tmp_path / "plant-key.json"
        self.key_hash_path = tmp_path / "plant-key.sha256"
        self.sonnet_directory = tmp_path / "sonnet"
        self.opus_directory = tmp_path / "opus"
        self.output_path = tmp_path / "flags.json"
        self.packets_path.write_text(
            ReportLinkCheckPackets(
                [
                    _build_packet(packet_id)
                    for packet_id in (*_REAL_PACKET_IDS, *_PLANT_PACKET_IDS)
                ]
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )
        key_bytes = (
            ReportLinkCheckKey(
                seed=1,
                plants=[
                    ReportLinkCheckPlant(
                        packet_id=packet_id,
                        kind=ReportLinkPlantKind.OTHER_REPORT_SAME_DATE,
                        true_target_report_id=f"true-{packet_id}",
                    )
                    for packet_id in _PLANT_PACKET_IDS
                ],
            )
            .model_dump_json(indent=2)
            .encode("utf-8")
        )
        self.key_path.write_bytes(key_bytes)
        self.key_hash_path.write_text(
            f"{hashlib.sha256(key_bytes).hexdigest()}\n", encoding="utf-8"
        )

    def run(self) -> None:
        list_report_link_flags(
            self.packets_path,
            self.key_path,
            self.key_hash_path,
            self.sonnet_directory,
            self.opus_directory,
            self.output_path,
        )

    def read_flags(self) -> ReportLinkCheckFlags:
        return ReportLinkCheckFlags.model_validate_json(
            self.output_path.read_text(encoding="utf-8")
        )


@pytest.fixture
def log_recorder(monkeypatch: pytest.MonkeyPatch) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(list_report_link_flags_script, "logger", recorder)
    return recorder


@pytest.fixture
def inputs(tmp_path: Path) -> _Inputs:
    return _Inputs(tmp_path)


def test_a_clean_run_writes_no_flags_and_scores_each_readers_recall(
    inputs: _Inputs, log_recorder: _LogRecorder
) -> None:
    sonnet_verdicts = {
        **_get_all_right(),
        "plant-1": ReportLinkVerdict.WRONG,
        "plant-2": ReportLinkVerdict.UNSURE,
    }
    opus_verdicts = {**_get_all_right(), "plant-1": ReportLinkVerdict.WRONG}
    _write_verdicts(inputs.sonnet_directory, sonnet_verdicts)
    _write_verdicts(inputs.opus_directory, opus_verdicts)

    inputs.run()

    assert inputs.read_flags().root == []
    assert "sonnet: caught 2 of 2 plants, missed []" in log_recorder.messages
    assert "opus: caught 1 of 2 plants, missed ['plant-2']" in log_recorder.messages


def test_a_verdict_that_is_not_right_on_a_real_packet_flags_it(
    inputs: _Inputs, log_recorder: _LogRecorder
) -> None:
    _write_verdicts(inputs.sonnet_directory, _get_all_right())
    _write_verdicts(
        inputs.opus_directory, {**_get_all_right(), "real-2": ReportLinkVerdict.UNSURE}
    )

    inputs.run()

    flags = inputs.read_flags().root
    assert [flag.packet_id for flag in flags] == ["real-2"]
    assert (
        flags[0].what_the_data_says == "The link points to Target real-2, 2020-03-03."
    )
    assert flags[0].reader_notes == ["opus: UNSURE: note real-2"]
    assert flags[0].group == "reply"
    assert flags[0].printed_citation == "citation real-2"


def test_a_plant_is_left_out_of_the_flags(
    inputs: _Inputs, log_recorder: _LogRecorder
) -> None:
    _write_verdicts(
        inputs.sonnet_directory,
        {**_get_all_right(), "plant-1": ReportLinkVerdict.WRONG},
    )
    _write_verdicts(
        inputs.opus_directory, {**_get_all_right(), "plant-1": ReportLinkVerdict.WRONG}
    )

    inputs.run()

    assert inputs.read_flags().root == []


def test_one_right_and_one_wrong_still_flags_and_notes_only_the_wrong(
    inputs: _Inputs, log_recorder: _LogRecorder
) -> None:
    _write_verdicts(
        inputs.sonnet_directory, {**_get_all_right(), "real-1": ReportLinkVerdict.WRONG}
    )
    _write_verdicts(inputs.opus_directory, _get_all_right())

    inputs.run()

    flags = inputs.read_flags().root
    assert [flag.packet_id for flag in flags] == ["real-1"]
    assert flags[0].reader_notes == ["sonnet: WRONG: note real-1"]


def test_a_tampered_key_raises(inputs: _Inputs, log_recorder: _LogRecorder) -> None:
    _write_verdicts(inputs.sonnet_directory, _get_all_right())
    _write_verdicts(inputs.opus_directory, _get_all_right())
    inputs.key_path.write_bytes(inputs.key_path.read_bytes() + b" ")

    with pytest.raises(HansardReportLinkCheckError, match="The plant key hashes to"):
        inputs.run()

    assert not inputs.output_path.exists()


def test_a_missing_verdict_raises(inputs: _Inputs, log_recorder: _LogRecorder) -> None:
    without_real_two = {
        packet_id: verdict
        for packet_id, verdict in _get_all_right().items()
        if packet_id != "real-2"
    }
    _write_verdicts(inputs.sonnet_directory, without_real_two)
    _write_verdicts(inputs.opus_directory, _get_all_right())

    with pytest.raises(
        HansardReportLinkCheckError, match=r"sonnet has no verdict for 1 packets"
    ):
        inputs.run()


def test_a_repeated_verdict_raises(inputs: _Inputs, log_recorder: _LogRecorder) -> None:
    _write_verdicts(inputs.sonnet_directory, _get_all_right())
    _write_verdicts(inputs.opus_directory, _get_all_right())
    repeat_directory = inputs.opus_directory / "batch-02"
    repeat_directory.mkdir()
    (repeat_directory / "verdicts.jsonl").write_text(
        json.dumps({"packet_id": "real-1", "verdict": "RIGHT", "note": "again"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        HansardReportLinkCheckError,
        match=r"opus wrote more than one verdict for 1 packets",
    ):
        inputs.run()


def test_an_unknown_verdict_raises(inputs: _Inputs, log_recorder: _LogRecorder) -> None:
    _write_verdicts(
        inputs.sonnet_directory,
        {**_get_all_right(), "stranger": ReportLinkVerdict.RIGHT},
    )
    _write_verdicts(inputs.opus_directory, _get_all_right())

    with pytest.raises(
        HansardReportLinkCheckError,
        match=r"sonnet wrote verdicts for 1 packets that do not exist",
    ):
        inputs.run()


def test_an_invalid_verdict_line_raises_naming_the_file_and_line(
    inputs: _Inputs, log_recorder: _LogRecorder
) -> None:
    _write_verdicts(inputs.sonnet_directory, _get_all_right())
    _write_verdicts(inputs.opus_directory, _get_all_right())
    verdicts_path = inputs.opus_directory / "batch-01" / "verdicts.jsonl"
    verdicts_path.write_text(
        verdicts_path.read_text(encoding="utf-8")
        + json.dumps({"packet_id": "real-1", "verdict": "MAYBE", "note": "x"})
        + "\n",
        encoding="utf-8",
    )
    invalid_line_number = len(_get_all_right()) + 1

    with pytest.raises(
        HansardReportLinkCheckError,
        match=rf"{verdicts_path}:{invalid_line_number} is not a valid verdict line",
    ):
        inputs.run()


def test_an_existing_output_file_raises(
    inputs: _Inputs, log_recorder: _LogRecorder
) -> None:
    _write_verdicts(inputs.sonnet_directory, _get_all_right())
    _write_verdicts(inputs.opus_directory, _get_all_right())
    inputs.output_path.write_text("kept", encoding="utf-8")

    with pytest.raises(FileExistsError):
        inputs.run()

    assert inputs.output_path.read_text(encoding="utf-8") == "kept"
