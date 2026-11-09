from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DivisionDetachment:
    division_id: int
    printed_counts: str
    ayes: int
    noes: int
    abstentions: Optional[int]
