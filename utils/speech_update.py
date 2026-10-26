from dataclasses import dataclass
from typing import Optional

from enums import SpeechKind


@dataclass(frozen=True)
class SpeechUpdate:
    id: int
    ordinal: int
    speaker: Optional[str]
    transcript: str
    kind: Optional[SpeechKind]
    speaker_id: Optional[int]
