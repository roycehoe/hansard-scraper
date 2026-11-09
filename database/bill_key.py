from typing import Optional

from sqlmodel import Field, SQLModel

import database.bill  # noqa: F401 registers Bill and Report so the foreign keys resolve


class BillKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    act_count: int

    bill_key: str = Field(foreign_key="report.report_id", unique=True)
    bill_id: int = Field(foreign_key="bill.id", unique=True)
