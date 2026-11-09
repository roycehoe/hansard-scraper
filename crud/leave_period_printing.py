from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlmodel import Session, col, delete, func, select

from database.leave_period import LeavePeriod, LeavePeriodPrinting
from database.speaker import Speaker
from enums import (
    LeaveEntryFormat,
    LeaveNameSource,
    LeaveOfficeSource,
    LeaveSpeakerLinkSource,
    LeaveYearSource,
)


@dataclass(frozen=True)
class LeavePeriodPrintingCount:
    entry_format: LeaveEntryFormat
    name_source: LeaveNameSource
    year_source: Optional[LeaveYearSource]
    printing_count: int


@dataclass(frozen=True)
class LeavePeriodPrintingCheckRow:
    id: int
    ordinal: int
    sitting_date: date
    printed_name: Optional[str]
    carried_name: Optional[str]
    printed_from: Optional[str]
    printed_to: Optional[str]
    printed_line: Optional[str]
    printed_heading_from: Optional[str]
    printed_heading_to: Optional[str]
    office_printed: Optional[str]
    entry_format: LeaveEntryFormat
    name_source: LeaveNameSource
    year_source: Optional[LeaveYearSource]
    speaker_link_source: Optional[LeaveSpeakerLinkSource]
    office_source: Optional[LeaveOfficeSource]
    sitting_id: int
    speaker_name: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    end_text: Optional[str]


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

    def get_check_rows(self) -> list[LeavePeriodPrintingCheckRow]:
        statement = (
            select(
                LeavePeriodPrinting.id,
                LeavePeriodPrinting.ordinal,
                LeavePeriodPrinting.sitting_date,
                LeavePeriodPrinting.printed_name,
                LeavePeriodPrinting.carried_name,
                LeavePeriodPrinting.printed_from,
                LeavePeriodPrinting.printed_to,
                LeavePeriodPrinting.printed_line,
                LeavePeriodPrinting.printed_heading_from,
                LeavePeriodPrinting.printed_heading_to,
                LeavePeriodPrinting.office_printed,
                LeavePeriodPrinting.entry_format,
                LeavePeriodPrinting.name_source,
                LeavePeriodPrinting.year_source,
                LeavePeriodPrinting.speaker_link_source,
                LeavePeriodPrinting.office_source,
                LeavePeriodPrinting.sitting_id,
                Speaker.name,
                LeavePeriod.start_date,
                LeavePeriod.end_date,
                LeavePeriod.end_text,
            )
            .join(
                LeavePeriod,
                col(LeavePeriod.id) == col(LeavePeriodPrinting.leave_period_id),
            )
            .join(
                Speaker,
                col(Speaker.id) == col(LeavePeriodPrinting.speaker_id),
                isouter=True,
            )
            .order_by(col(LeavePeriodPrinting.id))
        )
        return [
            LeavePeriodPrintingCheckRow(*row)
            for row in self.session.exec(statement).all()
        ]

    def delete_all(self) -> None:
        statement = delete(LeavePeriodPrinting)

        self.session.exec(statement)
