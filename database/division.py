from datetime import date
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.report  # noqa: F401 registers Report so the foreign key resolves
from enums import DivisionCountSource, DivisionListStatus


class Division(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "sprs_report_id",
            "report_division_number",
            name="uq_division_sprs_report_id_report_division_number",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    sitting_date: date = Field(index=True)
    parliament_number: int
    report_division_number: Optional[int] = None
    speech_ordinal: Optional[int] = None
    count_source: DivisionCountSource
    printed_counts: str
    ayes: Optional[int] = None
    noes: Optional[int] = None
    abstentions: Optional[int] = None
    absent: Optional[int] = None
    paired: Optional[int] = None
    list_status: DivisionListStatus
    printed_list: Optional[str] = None

    sprs_report_id: Optional[str] = Field(
        default=None, foreign_key="report.report_id", index=True
    )
