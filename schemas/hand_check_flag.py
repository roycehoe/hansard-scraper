from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel

from enums import HandCheckFlagReason, HandCheckMatchStatus
from schemas.hand_check_packet import HandCheckWordDifference
from schemas.hand_check_verdict import HandCheckVerdict


class HandCheckFlag(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    speech_id: int
    run_number: int
    reasons: list[HandCheckFlagReason]
    sonnet_speaker_verdict: Optional[HandCheckVerdict]
    opus_speaker_verdict: Optional[HandCheckVerdict]
    word_differences: list[HandCheckWordDifference]
    match_status: HandCheckMatchStatus


class HandCheckFlags(RootModel[list[HandCheckFlag]]):
    model_config = ConfigDict(frozen=True)
