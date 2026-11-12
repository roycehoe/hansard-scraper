from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel


class UnlabelledSpeechRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: int
    speaker: Optional[str]
    first_transcript_start: str
    last_transcript_start: str
    reason: str


class UnlabelledSpeechRanges(RootModel[list[UnlabelledSpeechRange]]):
    model_config = ConfigDict(frozen=True)
