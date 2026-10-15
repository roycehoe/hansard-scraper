from typing import Optional

from pydantic import BaseModel


class UnattributedSpeechRange(BaseModel):
    report_id: int
    speaker: Optional[str]
    first_transcript_start: str
    last_transcript_start: str
    reason: str
