from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BillJoinUpdate:
    id: int
    title: str
    last_sitting_date: datetime
    is_passed: bool
