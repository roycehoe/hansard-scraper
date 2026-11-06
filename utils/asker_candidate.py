from dataclasses import dataclass
from typing import Optional

from enums import ReportAskerSource


@dataclass(frozen=True)
class AskerCandidate:
    row_ordinal: int
    source: ReportAskerSource
    printed_name: str
    speaker_id: Optional[int]
    reader_printed_name: Optional[str]
    reader_speaker_id: Optional[int]
    reader_row_ordinal: Optional[int]
