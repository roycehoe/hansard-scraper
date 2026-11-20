from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import PrintedPlaceRule


class PlannedPrintedPlace(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: int
    sprs_report_id: str
    sitting_date: datetime
    printed_place: Optional[int]
    printed_place_rule: PrintedPlaceRule


class PrintedPlaceRuleCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_version: str
    report_type: str
    printed_place_rule: PrintedPlaceRule
    report_count: int


class SpeechNumberAgreement(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_version: str
    pair_count: int
    agreeing_pair_count: int


class PrintedPlacePlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    sitting_dates: list[datetime]
    printed_places: list[PlannedPrintedPlace]
    rule_counts: list[PrintedPlaceRuleCount]
    speech_number_agreements: list[SpeechNumberAgreement]
