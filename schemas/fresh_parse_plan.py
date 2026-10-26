from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel

from enums import SpeechKind


class HeldReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: int
    reason: str


class HeldReports(RootModel[list[HeldReport]]):
    pass


class SpeechRowUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    ordinal: int
    speaker: Optional[str]
    transcript: str
    kind: Optional[SpeechKind]
    is_speaker_changed: bool
    is_transcript_changed: bool
    is_ordinal_changed: bool


class SpeechRowInsert(BaseModel):
    model_config = ConfigDict(frozen=True)

    ordinal: int
    speaker: Optional[str]
    transcript: str
    kind: SpeechKind


class ReportFreshParsePlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: int
    stored_digest: str
    stored_row_count: int
    parsed_row_count: int
    markdown_content: Optional[str]
    updates: tuple[SpeechRowUpdate, ...]
    deletes: tuple[int, ...]
    inserts: tuple[SpeechRowInsert, ...]


class FreshParsePlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_plans: tuple[ReportFreshParsePlan, ...]
    held_report_ids: tuple[int, ...]
    kind_only_report_ids: tuple[int, ...]
    unparsed_report_ids_with_rows: tuple[int, ...]
