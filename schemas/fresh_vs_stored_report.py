from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel

from enums import SpeechKind


class FreshVsStoredStatus(StrEnum):
    SAME = "SAME"
    ORDINAL_ONLY = "ORDINAL_ONLY"
    CONTENT = "CONTENT"
    NO_CONTENT = "NO_CONTENT"
    NO_START_LINE = "NO_START_LINE"
    ERROR = "ERROR"


class ComparedSpeechRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    speaker: Optional[str]
    transcript: str
    kind: Optional[SpeechKind]


class DifferingBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    tag: str
    stored_start: int
    stored_end: int
    fresh_start: int
    fresh_end: int
    stored_rows: tuple[ComparedSpeechRow, ...]
    fresh_rows: tuple[ComparedSpeechRow, ...]


class RowDifferences(BaseModel):
    model_config = ConfigDict(frozen=True)

    blocks: tuple[DifferingBlock, ...]
    tokens_lost: dict[str, int]
    tokens_gained: dict[str, int]
    word_lost_count: int
    word_gained_count: int
    is_kind_only: bool
    is_kind_null_only: bool
    stored_rows: tuple[ComparedSpeechRow, ...]
    fresh_rows: tuple[ComparedSpeechRow, ...]


class FreshVsStoredReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    report_id: str
    report_type: str
    report_version: str
    parliament_number: int
    title: str
    held_reason: Optional[str]
    status: FreshVsStoredStatus
    stored_row_count: int
    fresh_row_count: Optional[int]
    is_markdown_different: Optional[bool]
    error: Optional[str]
    differences: Optional[RowDifferences]


class FreshVsStoredReports(RootModel[list[FreshVsStoredReport]]):
    pass
