from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class PrintedCitation:
    report_id: int
    ordinal: int
    printed_citation: str
    printed_title: Optional[str]
    printed_date: Optional[date]
    paragraph: str


@dataclass(frozen=True)
class ResumptionHeading:
    report_id: int
    ordinal: int
    printed_citation: str
    printed_date: Optional[date]
    paragraph: str
