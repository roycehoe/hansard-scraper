import hashlib
from pathlib import Path
from typing import Optional

import pytest

from enums import (
    AttachedFileCheckAnswer,
    AttachedFileCheckPlantKind,
    AttachedFileKind,
    ParagraphTieRule,
)
from exceptions import HansardAttachedFileError
from schemas.attached_file_check import (
    AttachedFileCheckFlags,
    AttachedFileCheckKey,
    AttachedFileCheckPacket,
    AttachedFileCheckPackets,
    AttachedFileCheckPlant,
    AttachedFileCheckVerdict,
)
from scripts.list_attached_file_flags import list_attached_file_flags

_ROUND_NUMBER = 2
_RIGHT = AttachedFileCheckAnswer.RIGHT
_WRONG = AttachedFileCheckAnswer.WRONG
_UNSURE = AttachedFileCheckAnswer.UNSURE
_WITH_FILE = "with-file"
_NO_FILE = "no-file"
_PARAGRAPH_PLANT_WITH_WORDS = "plant-words"
_PARAGRAPH_PLANT_WITHOUT_WORDS = "plant-no-words"
_FILE_PLANT = "plant-file"
_SHOWN_FILE_PACKET_IDS = (
    _WITH_FILE,
    _PARAGRAPH_PLANT_WITH_WORDS,
    _PARAGRAPH_PLANT_WITHOUT_WORDS,
    _FILE_PLANT,
)
_PACKET_IDS = (
    _WITH_FILE,
    _NO_FILE,
    _PARAGRAPH_PLANT_WITH_WORDS,
    _PARAGRAPH_PLANT_WITHOUT_WORDS,
    _FILE_PLANT,
)


def _build_packet(packet_id: str, ordinal: int) -> AttachedFileCheckPacket:
    has_file = packet_id in _SHOWN_FILE_PACKET_IDS
    return AttachedFileCheckPacket(
        packet_id=packet_id,
        sprs_report_id=f"report-{ordinal}",
        pointer_ordinal=ordinal,
        paragraph_tie_rule=ParagraphTieRule.ONLY_OCCURRENCE,
        speech_ordinal=ordinal,
        attached_file_id=ordinal if has_file else None,
        report_title="Title",
        link_words="Annex A",
        source_paragraph="See Annex A",
        row_speaker=None,
        row_transcript="See Annex A",
        file_kind=AttachedFileKind.ANNEX if has_file else None,
        file_title="Annex A" if has_file else None,
    )


def _build_verdict(
    packet_id: str,
    paragraph_answer: AttachedFileCheckAnswer = _RIGHT,
    file_answer: Optional[AttachedFileCheckAnswer] = None,
) -> AttachedFileCheckVerdict:
    if file_answer is None and packet_id in _SHOWN_FILE_PACKET_IDS:
        file_answer = _RIGHT
    return AttachedFileCheckVerdict(
        packet_id=packet_id,
        paragraph_answer=paragraph_answer,
        file_answer=file_answer,
        note="",
    )


def _write_verdicts(directory: Path, verdicts: list[AttachedFileCheckVerdict]) -> Path:
    directory.mkdir(parents=True)
    (directory / "verdicts.jsonl").write_text(
        "".join(f"{verdict.model_dump_json()}\n" for verdict in verdicts),
        encoding="utf-8",
    )
    return directory


def _write_inputs(directory: Path) -> tuple[Path, Path, Path]:
    packets_path = directory / "packets.json"
    packets_path.write_text(
        AttachedFileCheckPackets(
            [
                _build_packet(packet_id, ordinal)
                for ordinal, packet_id in enumerate(_PACKET_IDS, 1)
            ]
        ).model_dump_json(),
        encoding="utf-8",
    )
    key_bytes = (
        AttachedFileCheckKey(
            round_number=_ROUND_NUMBER,
            seed=1,
            packet_id_to_pointer_id={},
            plants=[
                AttachedFileCheckPlant(
                    packet_id=_PARAGRAPH_PLANT_WITH_WORDS,
                    kind=AttachedFileCheckPlantKind.PARAGRAPH,
                    true_speech_ordinal=1,
                    true_attached_file_id=1,
                    is_row_holding_link_words=True,
                ),
                AttachedFileCheckPlant(
                    packet_id=_PARAGRAPH_PLANT_WITHOUT_WORDS,
                    kind=AttachedFileCheckPlantKind.PARAGRAPH,
                    true_speech_ordinal=1,
                    true_attached_file_id=1,
                    is_row_holding_link_words=False,
                ),
                AttachedFileCheckPlant(
                    packet_id=_FILE_PLANT,
                    kind=AttachedFileCheckPlantKind.FILE,
                    true_speech_ordinal=None,
                    true_attached_file_id=1,
                    is_row_holding_link_words=None,
                ),
            ],
        )
        .model_dump_json()
        .encode("utf-8")
    )
    key_path = directory / "key.json"
    key_path.write_bytes(key_bytes)
    key_hash_path = directory / "key.sha256"
    key_hash_path.write_text(
        f"{hashlib.sha256(key_bytes).hexdigest()}\n", encoding="utf-8"
    )
    return packets_path, key_path, key_hash_path


def _get_caught_verdicts() -> list[AttachedFileCheckVerdict]:
    return [
        _build_verdict(_WITH_FILE),
        _build_verdict(_NO_FILE),
        _build_verdict(_PARAGRAPH_PLANT_WITH_WORDS, paragraph_answer=_WRONG),
        _build_verdict(_PARAGRAPH_PLANT_WITHOUT_WORDS, paragraph_answer=_WRONG),
        _build_verdict(_FILE_PLANT, file_answer=_WRONG),
    ]


def _run(
    directory: Path,
    sonnet_verdicts: list[AttachedFileCheckVerdict],
    opus_verdicts: list[AttachedFileCheckVerdict],
) -> tuple[Path, Path]:
    packets_path, key_path, key_hash_path = _write_inputs(directory)
    output_path = directory / "flags.json"
    summary_path = directory / "summary.txt"
    list_attached_file_flags(
        packets_path,
        key_path,
        key_hash_path,
        _write_verdicts(directory / "sonnet", sonnet_verdicts),
        _write_verdicts(directory / "opus", opus_verdicts),
        output_path,
        summary_path,
    )
    return output_path, summary_path


def _read_flag_packet_ids(output_path: Path) -> list[str]:
    return [
        flag.packet_id
        for flag in AttachedFileCheckFlags.model_validate_json(
            output_path.read_text(encoding="utf-8")
        ).root
    ]


def test_a_clean_run_writes_no_flags_and_the_summary(tmp_path: Path) -> None:
    output_path, summary_path = _run(
        tmp_path, _get_caught_verdicts(), _get_caught_verdicts()
    )

    assert _read_flag_packet_ids(output_path) == []
    assert "Flags: 0" in summary_path.read_text(encoding="utf-8")


def test_a_wrong_key_hash_refuses(tmp_path: Path) -> None:
    packets_path, key_path, key_hash_path = _write_inputs(tmp_path)
    key_hash_path.write_text("0" * 64, encoding="utf-8")

    with pytest.raises(HansardAttachedFileError, match="hashes to"):
        list_attached_file_flags(
            packets_path,
            key_path,
            key_hash_path,
            _write_verdicts(tmp_path / "sonnet", _get_caught_verdicts()),
            _write_verdicts(tmp_path / "opus", _get_caught_verdicts()),
            tmp_path / "flags.json",
            tmp_path / "summary.txt",
        )


def test_a_missing_verdict_refuses(tmp_path: Path) -> None:
    with pytest.raises(HansardAttachedFileError, match="Opus has no verdict for 1"):
        _run(tmp_path, _get_caught_verdicts(), _get_caught_verdicts()[1:])


def test_a_doubled_verdict_refuses(tmp_path: Path) -> None:
    with pytest.raises(HansardAttachedFileError, match="Sonnet wrote more than one"):
        _run(
            tmp_path,
            [*_get_caught_verdicts(), _build_verdict(_NO_FILE)],
            _get_caught_verdicts(),
        )


def test_null_on_a_packet_with_a_file_refuses(tmp_path: Path) -> None:
    verdicts = _get_caught_verdicts()
    verdicts[0] = AttachedFileCheckVerdict(
        packet_id=_WITH_FILE,
        paragraph_answer=_RIGHT,
        file_answer=None,
        note="",
    )

    with pytest.raises(HansardAttachedFileError, match="Sonnet gave a file answer"):
        _run(tmp_path, verdicts, _get_caught_verdicts())


def test_an_answer_on_a_packet_without_a_file_refuses(tmp_path: Path) -> None:
    verdicts = _get_caught_verdicts()
    verdicts[1] = _build_verdict(_NO_FILE, file_answer=_RIGHT)

    with pytest.raises(HansardAttachedFileError, match="Opus gave a file answer"):
        _run(tmp_path, _get_caught_verdicts(), verdicts)


def test_null_on_a_packet_without_a_file_passes(tmp_path: Path) -> None:
    output_path, _ = _run(tmp_path, _get_caught_verdicts(), _get_caught_verdicts())

    assert output_path.exists()


def test_an_unsure_answer_flags_a_row(tmp_path: Path) -> None:
    verdicts = _get_caught_verdicts()
    verdicts[0] = _build_verdict(_WITH_FILE, file_answer=_UNSURE)

    output_path, _ = _run(tmp_path, _get_caught_verdicts(), verdicts)

    assert _read_flag_packet_ids(output_path) == [_WITH_FILE]


def test_a_wrong_paragraph_answer_from_one_reader_flags_a_row(tmp_path: Path) -> None:
    verdicts = _get_caught_verdicts()
    verdicts[1] = _build_verdict(_NO_FILE, paragraph_answer=_WRONG)

    output_path, _ = _run(tmp_path, verdicts, _get_caught_verdicts())

    assert _read_flag_packet_ids(output_path) == [_NO_FILE]


def test_a_plant_is_left_out_of_the_flags(tmp_path: Path) -> None:
    output_path, _ = _run(tmp_path, _get_caught_verdicts(), _get_caught_verdicts())

    assert _read_flag_packet_ids(output_path) == []


def test_a_missed_plant_is_reported_by_reader_and_group(tmp_path: Path) -> None:
    missed_verdicts = _get_caught_verdicts()
    missed_verdicts[3] = _build_verdict(_PARAGRAPH_PLANT_WITHOUT_WORDS)

    _, summary_path = _run(tmp_path, _get_caught_verdicts(), missed_verdicts)

    summary = summary_path.read_text(encoding="utf-8")
    sonnet_part, opus_part = summary.split("Opus recall")
    assert (
        "paragraph plants on a row without the link words: caught 1 of 1" in sonnet_part
    )
    assert (
        "paragraph plants on a row without the link words: caught 0 of 1" in opus_part
    )
    assert f"missed packet {_PARAGRAPH_PLANT_WITHOUT_WORDS}" in opus_part
    assert (
        "paragraph plants on a row holding the link words: caught 1 of 1" in opus_part
    )
    assert "file plants: caught 1 of 1" in opus_part


def test_an_existing_output_refuses(tmp_path: Path) -> None:
    (tmp_path / "flags.json").write_text("[]", encoding="utf-8")

    with pytest.raises(HansardAttachedFileError, match="already exists"):
        _run(tmp_path, _get_caught_verdicts(), _get_caught_verdicts())
