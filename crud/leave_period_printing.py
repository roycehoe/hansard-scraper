from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session, col, delete, func, select

from database.leave_period import LeavePeriodPrinting
from enums import LeaveEntryFormat, LeaveNameSource, LeaveYearSource


@dataclass(frozen=True)
class LeavePeriodPrintingCount:
    entry_format: LeaveEntryFormat
    name_source: LeaveNameSource
    year_source: Optional[LeaveYearSource]
    printing_count: int


class CRUDLeavePeriodPrinting:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, leave_period_printings: list[LeavePeriodPrinting]) -> None:
        self.session.add_all(leave_period_printings)
        self.session.flush()

    def get_entry_format_and_name_source_and_year_source_counts(
        self,
    ) -> list[LeavePeriodPrintingCount]:
        statement = select(
            LeavePeriodPrinting.entry_format,
            LeavePeriodPrinting.name_source,
            LeavePeriodPrinting.year_source,
            func.count(),
        ).group_by(
            col(LeavePeriodPrinting.entry_format),
            col(LeavePeriodPrinting.name_source),
            col(LeavePeriodPrinting.year_source),
        )
        return [
            LeavePeriodPrintingCount(*row) for row in self.session.exec(statement).all()
        ]

    def delete_all(self) -> int:
        statement = delete(LeavePeriodPrinting)

        return self.session.exec(statement).rowcount
