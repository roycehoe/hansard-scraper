from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from enums import ReportType, ReportVersion, SpeechKind
from schemas.hand_check_snapshot import (
    HandCheckFrameSummary,
    HandCheckSnapshot,
    HandCheckSnapshotRow,
    HandCheckSnapshotRows,
)


def _build_row() -> HandCheckSnapshotRow:
    return HandCheckSnapshotRow(
        speech_id=1_090_144,
        report_id=35_800,
        hansard_report_id="00069257-ZZ.00055026-ZZ_1#id003_19720322_S0007_T00171-speaker#",
        html_file_name="00069257-ZZ.00055026-ZZ_1.htm",
        report_version=ReportVersion.SPRS2,
        report_type=ReportType.MOTION,
        parliament_number=3,
        sitting_date=datetime(1972, 3, 22),
        report_title="Motion title",
        ordinal=3,
        speaker="Mr Speaker",
        speaker_id=77,
        speaker_name="Yeoh Ghim Seng",
        person_name="Yeoh Ghim Seng",
        kind=SpeechKind.SPEECH,
        transcript="Order, order.",
        next_speaker="Mr Lee",
        next_transcript="Sir, I beg to move.",
    )


def _build_last_row() -> HandCheckSnapshotRow:
    return _build_row().model_copy(
        update={
            "html_file_name": None,
            "speaker": None,
            "person_name": None,
            "kind": None,
            "next_speaker": None,
            "next_transcript": None,
        }
    )


def _build_frame_summary(read_at: datetime) -> HandCheckFrameSummary:
    return HandCheckFrameSummary(
        database_label="db.example.org:6543/hansard",
        read_at=read_at,
        seed=20_261_102,
        sample_size=1_000,
        group_to_frame_count={"Parliaments 0 to 11": 800, "Parliament 12": 200},
        group_to_allocation={"Parliaments 0 to 11": 800, "Parliament 12": 200},
        group_to_start={"Parliaments 0 to 11": "5/4", "Parliament 12": "0"},
        frame_hash="0" * 64,
        weight_spread="0",
    )


def test_the_snapshot_file_reads_back_to_an_equal_snapshot() -> None:
    snapshot = HandCheckSnapshot(
        frame=_build_frame_summary(datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)),
        rows=[_build_row(), _build_last_row()],
    )

    assert HandCheckSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot


def test_the_plant_file_reads_back_to_equal_rows() -> None:
    rows = HandCheckSnapshotRows([_build_row(), _build_last_row()])

    assert HandCheckSnapshotRows.model_validate_json(rows.model_dump_json()) == rows


@pytest.mark.parametrize(
    "field",
    [
        "html_file_name",
        "speaker",
        "person_name",
        "kind",
        "next_speaker",
        "next_transcript",
    ],
)
def test_a_snapshot_row_refuses_a_missing_optional_field(field: str) -> None:
    data = _build_row().model_dump()
    del data[field]

    with pytest.raises(ValidationError, match=field):
        HandCheckSnapshotRow.model_validate(data)


def test_a_frame_summary_refuses_a_read_time_without_a_timezone() -> None:
    with pytest.raises(ValidationError, match="read_at"):
        _build_frame_summary(datetime(2026, 11, 2, 9, 30))
