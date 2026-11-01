from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

from enums import (
    HandCheckDifferenceClass,
    HandCheckErrorTier,
    HandCheckSpeakerVerdict,
)


class HandCheckVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str
    speaker_verdict: HandCheckSpeakerVerdict
    speaker_tier: Optional[HandCheckErrorTier]
    note: str
    difference_classes: list[HandCheckDifferenceClass] = []

    @model_validator(mode="after")
    def _validate_speaker_tier(self) -> "HandCheckVerdict":
        if (
            self.speaker_verdict == HandCheckSpeakerVerdict.WRONG
            and self.speaker_tier is None
        ):
            raise ValueError("a wrong speaker verdict needs a speaker_tier")
        if (
            self.speaker_verdict != HandCheckSpeakerVerdict.WRONG
            and self.speaker_tier is not None
        ):
            raise ValueError("only a wrong speaker verdict takes a speaker_tier")
        return self
