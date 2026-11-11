from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import (
    DivisionListStatus,
    DivisionReviewItemKind,
    MinutesDivisionPairing,
)


class DivisionReviewItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: DivisionReviewItemKind
    sitting_date: date
    division_id: Optional[int]
    minutes_id: Optional[int]
    sprs_report_id: Optional[str]
    source_text: str
    data_says: str
    rule: str


class DivisionListStatusCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    decade: str
    list_status: DivisionListStatus
    division_count: int


class MinutesDivisionPairingCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    pairing: MinutesDivisionPairing
    minutes_division_count: int


class DivisionReviewList(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[DivisionReviewItem]
    kind_to_count: dict[DivisionReviewItemKind, int]
    list_status_counts: list[DivisionListStatusCount]
    pairing_counts: list[MinutesDivisionPairingCount]
