from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SittingSpanUpdate:
    id: int
    first_sitting_date: date
    last_sitting_date: date
    sitting_count: int
