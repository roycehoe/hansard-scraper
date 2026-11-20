from dataclasses import dataclass
from typing import Optional

from enums import PrintedPlaceRule


@dataclass(frozen=True)
class PrintedPlaceUpdate:
    id: int
    printed_place: Optional[int]
    printed_place_rule: PrintedPlaceRule
