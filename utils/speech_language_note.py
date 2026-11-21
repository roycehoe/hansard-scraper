from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SpeechLanguageNoteChange:
    id: int
    ordinal: int
    speaker: Optional[str]
    transcript: str
    language_note: Optional[str]
