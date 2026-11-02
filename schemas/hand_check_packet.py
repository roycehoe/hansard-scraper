from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel

from enums import (
    HandCheckDifferenceKind,
    HandCheckLiveCheckStatus,
    HandCheckMatchStatus,
)
from schemas.hand_check_office_holder import HandCheckOfficeHolder
from schemas.hand_check_snapshot import HandCheckSnapshotRow


class HandCheckWordDifference(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation: str
    source_words: str
    row_words: str
    kind: Optional[HandCheckDifferenceKind] = None


class HandCheckGapCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_next_row: bool
    skipped_paragraphs: list[str]
    next_source_text: Optional[str]


class HandCheckRoleSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_chair_label: bool
    office: Optional[str]
    office_holders: list[HandCheckOfficeHolder]
    chair_marks: list[str]


class HandCheckPacket(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    snapshot: HandCheckSnapshotRow
    official_record_url: str
    match_status: HandCheckMatchStatus
    matched_source_html: str
    context_paragraphs: list[str]
    after_paragraph: Optional[str]
    word_differences: list[HandCheckWordDifference]
    gap_check: Optional[HandCheckGapCheck]
    role_section: Optional[HandCheckRoleSection]
    live_check_status: Optional[HandCheckLiveCheckStatus]
    live_match_status: Optional[HandCheckMatchStatus]


class HandCheckPackets(RootModel[list[HandCheckPacket]]):
    model_config = ConfigDict(frozen=True)
