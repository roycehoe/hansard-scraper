from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.report  # noqa: F401 registers Report so the foreign key resolves
from enums import ActNumberSource, BillClass, BillNumberSource


class Bill(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    title: str
    title_key: str = Field(index=True)
    first_sitting_date: datetime
    last_sitting_date: datetime
    bill_number: Optional[str] = Field(default=None, index=True)
    bill_number_source: Optional[BillNumberSource] = None
    bill_class: Optional[BillClass] = None
    act_number: Optional[str] = None
    act_number_source: Optional[ActNumberSource] = None

    is_passed: bool


class BillReport(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "bill_id", "report_id", name="uq_billreport_bill_id_report_id"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    bill_id: int = Field(foreign_key="bill.id", index=True)
    report_id: int = Field(foreign_key="report.id", index=True)
