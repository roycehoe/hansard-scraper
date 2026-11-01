import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest
from pydantic import ValidationError

import scripts.build_hand_check_plants as build_hand_check_plants_script
from crud.speech import SpeechParseRow, SpeechSnapshotRow, SpeechTranscriptRow
from database.speaker import Speaker
from enums import HandCheckPlantKind, ReportType, ReportVersion, SpeechKind
from schemas.hand_check_plant_key import HandCheckPlant, HandCheckPlantKey
from schemas.hand_check_snapshot import HandCheckSnapshotRow, HandCheckSnapshotRows

_PARLIAMENT_NUMBER = 12
_OTHER_PARLIAMENT_NUMBER = 13
_SOURCE_SPEECH_ID = 900
_SOURCE_ORDINAL = 4
_FRACTIONS = (0.0, 0.5, 0.99)


def _build_speaker(
    speaker_id: int,
    name: str,
    parliament_number: int,
    is_member: bool,
    person_id: Optional[int] = None,
) -> Speaker:
    return Speaker(
        id=speaker_id,
        name=name,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=parliament_number,
        is_member=is_member,
        person_id=person_id,
    )


def _build_row(
    row_id: int, ordinal: int, speaker_id: Optional[int], speaker: str = "Label"
) -> SpeechParseRow:
    return SpeechParseRow(
        id=row_id,
        report_id=1,
        ordinal=ordinal,
        speaker=speaker,
        transcript="text",
        kind=None,
        speaker_id=speaker_id,
    )


def _build_source(
    speaker: Optional[str], speaker_id: Optional[int], kind: SpeechKind
) -> SpeechSnapshotRow:
    return SpeechSnapshotRow(
        id=_SOURCE_SPEECH_ID,
        report_id=35_800,
        hansard_report_id="report-a",
        html_file_name=None,
        report_version=ReportVersion.SPRS3,
        report_type=ReportType.MOTION,
        parliament_number=_PARLIAMENT_NUMBER,
        sitting_date=datetime(2020, 1, 1),
        title="Motion title",
        ordinal=_SOURCE_ORDINAL,
        speaker=speaker,
        speaker_id=speaker_id,
        kind=kind,
        transcript="Some words.",
    )


def _build_lookups() -> build_hand_check_plants_script.CreditLookups:
    return build_hand_check_plants_script.CreditLookups(
        speaker_id_to_speaker={
            1: _build_speaker(1, "Lee Hsien Loong", _PARLIAMENT_NUMBER, True, 10),
            2: _build_speaker(2, "Pritam Singh", _PARLIAMENT_NUMBER, True, 20),
            3: _build_speaker(3, "Sylvia Lim", _PARLIAMENT_NUMBER, True),
        },
        person_id_to_canonical_name={
            10: "Lee Hsien Loong Canonical",
            20: "Pritam Singh Canonical",
        },
    )


def _build_key() -> HandCheckPlantKey:
    return HandCheckPlantKey(
        round_number=1,
        plants=[
            HandCheckPlant(
                speech_id=900,
                kind=HandCheckPlantKind.WRONG_MEMBER,
                original="Lee Hsien Loong",
                planted="Pritam Singh",
            ),
            HandCheckPlant(
                speech_id=901,
                kind=HandCheckPlantKind.CREDITED_NON_SPEECH_LINE,
                original="",
                planted="Sylvia Lim",
            ),
        ],
    )


def _build_procedural_rows() -> list[SpeechTranscriptRow]:
    return [
        SpeechTranscriptRow(id=4, transcript="Question put, and agreed to."),
        SpeechTranscriptRow(
            id=2, transcript="Resolved, That the Bill be read a Second time."
        ),
    ]


def _build_editorial_note_rows() -> list[SpeechTranscriptRow]:
    return [
        SpeechTranscriptRow(id=3, transcript="APPENDIX A (Cols. 395 - 398)"),
        SpeechTranscriptRow(id=5, transcript="[Mr Lee spoke in Mandarin.]"),
        SpeechTranscriptRow(id=1, transcript="Table 3 - Rates (Col. 12)"),
    ]


def test_the_nearest_credited_row_above_skips_uncredited_rows_and_rows_below() -> None:
    rows = [
        _build_row(1, 1, 1),
        _build_row(2, 2, None),
        _build_row(3, 3, 2),
        _build_row(4, 4, None),
        _build_row(5, 5, 3),
    ]

    nearest_above_ordinal_four = (
        build_hand_check_plants_script.get_nearest_credited_row_above(rows, 4)
    )
    nearest_above_ordinal_three = (
        build_hand_check_plants_script.get_nearest_credited_row_above(rows, 3)
    )

    assert nearest_above_ordinal_four == rows[2]
    assert nearest_above_ordinal_three == rows[0]


def test_no_credited_row_above_gives_none() -> None:
    rows = [_build_row(1, 1, 1), _build_row(2, 2, None), _build_row(3, 3, None)]
    uncredited_rows = [
        _build_row(1, 1, None),
        _build_row(2, 2, None),
        _build_row(3, 3, None),
    ]

    assert (
        build_hand_check_plants_script.get_nearest_credited_row_above(rows, 1) is None
    )
    assert (
        build_hand_check_plants_script.get_nearest_credited_row_above(
            uncredited_rows, 3
        )
        is None
    )


def test_the_next_row_is_the_one_after_it_in_the_list() -> None:
    rows = [_build_row(1, 5, 1), _build_row(2, 5, 1), _build_row(3, 6, 1)]

    assert build_hand_check_plants_script.get_next_row(rows, 1) == rows[1]
    assert build_hand_check_plants_script.get_next_row(rows, 2) == rows[2]


def test_the_last_row_of_a_report_has_no_next_row() -> None:
    rows = [_build_row(1, 5, 1), _build_row(2, 5, 1), _build_row(3, 6, 1)]

    assert build_hand_check_plants_script.get_next_row(rows, 3) is None
    assert build_hand_check_plants_script.get_next_row([], 1) is None


@pytest.mark.parametrize(
    "label",
    [
        "The Chairman",
        "Mr Chairman",
        "Mdm Speaker",
        "Mr Deputy Speaker",
        "The Deputy Speaker",
        "The Minister for Finance",
        "His Excellency the Governor",
        "the chairman",
    ],
)
def test_a_role_label_is_found_in_each_of_its_four_forms(label: str) -> None:
    assert build_hand_check_plants_script.is_role_label(label) is True


@pytest.mark.parametrize(
    "label",
    [
        "Mr Lee Hsien Loong",
        "Ms Sylvia Lim (Aljunied)",
        "The Minister for Health (Mr Khaw Boon Wan)",
        "Mr Deputy Speaker (Mr Charles Chong)",
        None,
    ],
)
def test_a_label_that_names_a_person_or_is_missing_is_not_a_role_label(
    label: Optional[str],
) -> None:
    assert build_hand_check_plants_script.is_role_label(label) is False


def test_the_non_speech_pool_takes_every_procedural_row_and_only_the_captions_among_editorial_notes() -> (
    None
):
    assert build_hand_check_plants_script.get_non_speech_speech_ids(
        _build_procedural_rows(), _build_editorial_note_rows(), set()
    ) == [1, 2, 3, 4]


def test_the_non_speech_pool_leaves_out_excluded_ids_and_is_ordered_by_speech_id() -> (
    None
):
    assert build_hand_check_plants_script.get_non_speech_speech_ids(
        _build_procedural_rows(), _build_editorial_note_rows(), {2, 3}
    ) == [1, 4]
    assert build_hand_check_plants_script.get_non_speech_speech_ids([], [], set()) == []


@pytest.mark.parametrize("fraction", _FRACTIONS)
def test_another_member_is_a_different_member_of_the_same_parliament(
    fraction: float,
) -> None:
    speaker_id_to_speaker = {
        1: _build_speaker(1, "Lee Hsien Loong", _PARLIAMENT_NUMBER, True),
        2: _build_speaker(2, "Lee Hsien Loong", _PARLIAMENT_NUMBER, True),
        3: _build_speaker(3, "Pritam Singh", _OTHER_PARLIAMENT_NUMBER, True),
        4: _build_speaker(4, "Halimah Yacob", _PARLIAMENT_NUMBER, False),
        5: _build_speaker(5, "Sylvia Lim", _PARLIAMENT_NUMBER, True),
    }

    assert [
        build_hand_check_plants_script.get_other_member_id(
            speaker_id_to_speaker,
            _PARLIAMENT_NUMBER,
            speaker_id_to_speaker[1],
            fraction,
        )
    ] == [5]


@pytest.mark.parametrize("fraction", _FRACTIONS)
def test_a_second_row_of_the_same_person_is_not_another_member(
    fraction: float,
) -> None:
    speaker_id_to_speaker = {
        1: _build_speaker(1, "Lee Hsien Loong", _PARLIAMENT_NUMBER, True, 10),
        2: _build_speaker(2, "L H Loong", _PARLIAMENT_NUMBER, True, 10),
        3: _build_speaker(3, "Pritam Singh", _PARLIAMENT_NUMBER, True, 20),
    }
    same_person_speaker_id_to_speaker = {
        1: speaker_id_to_speaker[1],
        2: speaker_id_to_speaker[2],
    }

    assert [
        build_hand_check_plants_script.get_other_member_id(
            speaker_id_to_speaker,
            _PARLIAMENT_NUMBER,
            speaker_id_to_speaker[1],
            fraction,
        )
    ] == [3]
    assert (
        build_hand_check_plants_script.get_other_member_id(
            same_person_speaker_id_to_speaker,
            _PARLIAMENT_NUMBER,
            speaker_id_to_speaker[1],
            fraction,
        )
        is None
    )


def test_a_parliament_with_one_member_has_no_other_member() -> None:
    speaker = _build_speaker(1, "Lee Hsien Loong", _PARLIAMENT_NUMBER, True)

    assert (
        build_hand_check_plants_script.get_other_member_id(
            {1: speaker}, _PARLIAMENT_NUMBER, speaker, 0.5
        )
        is None
    )


def test_the_fraction_picks_among_the_other_members_in_speaker_id_order() -> None:
    original_speaker = _build_speaker(1, "Lee Hsien Loong", _PARLIAMENT_NUMBER, True)
    speaker_id_to_speaker = {
        1: original_speaker,
        7: _build_speaker(7, "Pritam Singh", _PARLIAMENT_NUMBER, True),
        3: _build_speaker(3, "Sylvia Lim", _PARLIAMENT_NUMBER, True),
        9: _build_speaker(9, "Low Thia Khiang", _PARLIAMENT_NUMBER, True),
    }

    assert [
        build_hand_check_plants_script.get_other_member_id(
            speaker_id_to_speaker, _PARLIAMENT_NUMBER, original_speaker, fraction
        )
        for fraction in _FRACTIONS
    ] == [3, 7, 9]


def test_the_plant_key_is_written_with_the_sha256_of_its_bytes(
    tmp_path: Path,
) -> None:
    digest = build_hand_check_plants_script.write_plant_files(
        HandCheckSnapshotRows([]),
        _build_key(),
        tmp_path / "plants.json",
        tmp_path / "key.json",
        tmp_path / "key.sha256",
    )

    expected_digest = hashlib.sha256((tmp_path / "key.json").read_bytes()).hexdigest()
    assert (tmp_path / "key.sha256").read_text(
        encoding="utf-8"
    ) == expected_digest + "\n"
    assert digest == expected_digest


def test_a_written_plant_key_reads_back_equal(tmp_path: Path) -> None:
    key = _build_key()

    build_hand_check_plants_script.write_plant_files(
        HandCheckSnapshotRows([]),
        key,
        tmp_path / "plants.json",
        tmp_path / "key.json",
        tmp_path / "key.sha256",
    )

    assert (
        HandCheckPlantKey.model_validate_json(
            (tmp_path / "key.json").read_text(encoding="utf-8")
        )
        == key
    )


def test_an_existing_key_is_never_overwritten(tmp_path: Path) -> None:
    key_path = tmp_path / "key.json"
    hash_path = tmp_path / "key.sha256"
    key_path.write_text("sealed", encoding="utf-8")

    with pytest.raises(FileExistsError):
        build_hand_check_plants_script.write_plant_files(
            HandCheckSnapshotRows([]),
            _build_key(),
            tmp_path / "plants.json",
            key_path,
            hash_path,
        )

    assert key_path.read_text(encoding="utf-8") == "sealed"
    assert not hash_path.exists()


def test_an_existing_plants_file_is_never_overwritten_and_no_key_is_written(
    tmp_path: Path,
) -> None:
    plants_path = tmp_path / "plants.json"
    key_path = tmp_path / "key.json"
    hash_path = tmp_path / "key.sha256"
    plants_path.write_text("sealed plants", encoding="utf-8")

    with pytest.raises(FileExistsError):
        build_hand_check_plants_script.write_plant_files(
            HandCheckSnapshotRows([]), _build_key(), plants_path, key_path, hash_path
        )

    assert plants_path.read_text(encoding="utf-8") == "sealed plants"
    assert not key_path.exists()
    assert not hash_path.exists()


def test_a_snapshot_row_takes_the_credit_it_is_given_and_copies_the_rest() -> None:
    source = _build_source("Mr Lee", 1, SpeechKind.SPEECH)

    snapshot_row = build_hand_check_plants_script.build_snapshot_row(
        source, _build_row(901, 5, 2), "Given label", 2, "Given text.", _build_lookups()
    )

    assert snapshot_row == HandCheckSnapshotRow(
        speech_id=_SOURCE_SPEECH_ID,
        report_id=source.report_id,
        hansard_report_id=source.hansard_report_id,
        html_file_name=source.html_file_name,
        report_version=source.report_version,
        report_type=source.report_type,
        parliament_number=source.parliament_number,
        sitting_date=source.sitting_date,
        report_title=source.title,
        ordinal=_SOURCE_ORDINAL,
        speaker="Given label",
        speaker_id=2,
        speaker_name="Pritam Singh",
        person_name="Pritam Singh Canonical",
        kind=SpeechKind.SPEECH,
        transcript="Given text.",
        next_speaker="Label",
        next_transcript="text",
    )


def test_a_snapshot_row_for_a_speaker_with_no_person_and_no_next_row_holds_none() -> (
    None
):
    snapshot_row = build_hand_check_plants_script.build_snapshot_row(
        _build_source("Mr Lee", 1, SpeechKind.SPEECH),
        None,
        "Given label",
        3,
        "Given text.",
        _build_lookups(),
    )

    assert snapshot_row.person_name is None
    assert snapshot_row.next_speaker is None
    assert snapshot_row.next_transcript is None


def test_a_wrong_member_plant_changes_only_the_speaker_id_speaker_name_and_person_name() -> (
    None
):
    source = _build_source("Mr Lee", 1, SpeechKind.SPEECH)
    next_row = _build_row(901, 5, 2)
    lookups = _build_lookups()

    planted_row = build_hand_check_plants_script.plant_wrong_member(
        source, 1, next_row, 0.0, lookups
    )

    assert planted_row is not None
    assert (
        planted_row.snapshot_row
        == build_hand_check_plants_script.build_snapshot_row(
            source, next_row, "Mr Lee", 1, "Some words.", lookups
        ).model_copy(
            update={
                "speaker_id": 2,
                "speaker_name": "Pritam Singh",
                "person_name": "Pritam Singh Canonical",
            }
        )
    )
    assert planted_row.snapshot_row.speaker == "Mr Lee"
    assert planted_row.snapshot_row.transcript == "Some words."
    assert planted_row.snapshot_row.ordinal == _SOURCE_ORDINAL
    assert planted_row.snapshot_row.kind == SpeechKind.SPEECH
    assert planted_row.snapshot_row.next_speaker == "Label"
    assert planted_row.snapshot_row.next_transcript == "text"


def test_a_wrong_member_plant_records_both_names() -> None:
    source = _build_source("Mr Lee", 1, SpeechKind.SPEECH)
    next_row = _build_row(901, 5, 2)

    planted_row = build_hand_check_plants_script.plant_wrong_member(
        source, 1, next_row, 0.0, _build_lookups()
    )
    last_planted_row = build_hand_check_plants_script.plant_wrong_member(
        source, 1, next_row, 0.99, _build_lookups()
    )

    assert planted_row is not None
    assert planted_row.plant == HandCheckPlant(
        speech_id=_SOURCE_SPEECH_ID,
        kind=HandCheckPlantKind.WRONG_MEMBER,
        original="Lee Hsien Loong",
        planted="Pritam Singh",
    )
    assert last_planted_row is not None
    assert [last_planted_row.snapshot_row.speaker_id] == [3]
    assert last_planted_row.snapshot_row.person_name is None


def test_a_wrong_member_plant_is_none_when_the_parliament_has_no_other_member() -> None:
    lookups = build_hand_check_plants_script.CreditLookups(
        speaker_id_to_speaker={
            1: _build_speaker(1, "Lee Hsien Loong", _PARLIAMENT_NUMBER, True, 10)
        },
        person_id_to_canonical_name={10: "Lee Hsien Loong Canonical"},
    )

    assert (
        build_hand_check_plants_script.plant_wrong_member(
            _build_source("Mr Lee", 1, SpeechKind.SPEECH),
            1,
            _build_row(901, 5, 2),
            0.0,
            lookups,
        )
        is None
    )


def test_a_credited_non_speech_line_plant_takes_the_label_and_credit_of_the_nearest_credited_row_above() -> (
    None
):
    report_rows = [
        _build_row(899, 3, 1, speaker="Mr Lee"),
        _build_row(900, 4, None),
        _build_row(901, 5, 2),
    ]

    planted_row = build_hand_check_plants_script.plant_credited_non_speech_line(
        _build_source(None, None, SpeechKind.PROCEDURAL),
        report_rows,
        report_rows[2],
        _build_lookups(),
    )

    assert planted_row is not None
    assert planted_row.snapshot_row == HandCheckSnapshotRow(
        speech_id=_SOURCE_SPEECH_ID,
        report_id=35_800,
        hansard_report_id="report-a",
        html_file_name=None,
        report_version=ReportVersion.SPRS3,
        report_type=ReportType.MOTION,
        parliament_number=_PARLIAMENT_NUMBER,
        sitting_date=datetime(2020, 1, 1),
        report_title="Motion title",
        ordinal=_SOURCE_ORDINAL,
        speaker="Mr Lee",
        speaker_id=1,
        speaker_name="Lee Hsien Loong",
        person_name="Lee Hsien Loong Canonical",
        kind=SpeechKind.PROCEDURAL,
        transcript="Some words.",
        next_speaker="Label",
        next_transcript="text",
    )


def test_a_credited_non_speech_line_plant_records_no_original_and_the_credited_name() -> (
    None
):
    report_rows = [
        _build_row(899, 3, 1, speaker="Mr Lee"),
        _build_row(900, 4, None),
        _build_row(901, 5, 2),
    ]

    planted_row = build_hand_check_plants_script.plant_credited_non_speech_line(
        _build_source(None, None, SpeechKind.PROCEDURAL),
        report_rows,
        report_rows[2],
        _build_lookups(),
    )

    assert planted_row is not None
    assert planted_row.plant == HandCheckPlant(
        speech_id=_SOURCE_SPEECH_ID,
        kind=HandCheckPlantKind.CREDITED_NON_SPEECH_LINE,
        original="",
        planted="Lee Hsien Loong",
    )


def test_a_credited_non_speech_line_plant_is_none_when_no_credited_row_sits_above() -> (
    None
):
    report_rows = [_build_row(900, 4, None), _build_row(901, 5, 2)]

    assert (
        build_hand_check_plants_script.plant_credited_non_speech_line(
            _build_source(None, None, SpeechKind.PROCEDURAL),
            report_rows,
            report_rows[1],
            _build_lookups(),
        )
        is None
    )


def test_a_credited_non_speech_line_plant_is_none_when_the_credited_row_above_has_a_role_label() -> (
    None
):
    report_rows = [
        _build_row(899, 3, 1, speaker="The Chairman"),
        _build_row(900, 4, None),
        _build_row(901, 5, 2),
    ]

    assert (
        build_hand_check_plants_script.plant_credited_non_speech_line(
            _build_source(None, None, SpeechKind.PROCEDURAL),
            report_rows,
            report_rows[2],
            _build_lookups(),
        )
        is None
    )


@pytest.mark.parametrize(
    "kind",
    ["SWAPPED_NAME", "wrong_member", "DROPPED_WORD", "GLUED_WORDS", "CREDITED_CAPTION"],
)
def test_a_plant_key_refuses_an_unlisted_kind(kind: str) -> None:
    with pytest.raises(ValidationError):
        HandCheckPlant.model_validate(
            {"speech_id": 1, "kind": kind, "original": "a", "planted": "b"}
        )


def test_a_plant_missing_its_original_is_refused() -> None:
    with pytest.raises(ValidationError):
        HandCheckPlant.model_validate(
            {"speech_id": 1, "kind": "WRONG_MEMBER", "planted": "b"}
        )


def test_the_plant_kind_values_equal_their_member_names() -> None:
    assert [kind.value for kind in HandCheckPlantKind] == [
        "WRONG_MEMBER",
        "CREDITED_NON_SPEECH_LINE",
    ]
