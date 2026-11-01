from datetime import datetime
from typing import Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, RootModel

from enums import SpeechKind


class HandCheckSnapshotRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    speech_id: int
    report_id: int
    hansard_report_id: str
    html_file_name: Optional[str]
    report_version: str
    report_type: str
    parliament_number: int
    sitting_date: datetime
    report_title: str
    ordinal: int
    speaker: Optional[str]
    speaker_id: int
    speaker_name: str
    person_name: Optional[str]
    kind: Optional[SpeechKind]
    transcript: str
    next_speaker: Optional[str]
    next_transcript: Optional[str]


class HandCheckFrameSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_label: str
    read_at: AwareDatetime
    seed: int
    sample_size: int
    group_to_frame_count: dict[str, int]
    group_to_allocation: dict[str, int]
    group_to_start: dict[str, str]
    frame_hash: str
    weight_spread: str


class HandCheckSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    frame: HandCheckFrameSummary
    rows: list[HandCheckSnapshotRow]


class HandCheckSnapshotRows(RootModel[list[HandCheckSnapshotRow]]):
    model_config = ConfigDict(frozen=True)
