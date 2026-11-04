from datetime import date
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.bill  # noqa: F401 registers Bill so the foreign key resolves
from enums import ActHistoryEntryKind, BillLinkSource


class Act(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    sso_code: str = Field(unique=True)
    title: str


class ActHistoryEntry(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("act_id", "ordinal", name="uq_acthistoryentry_act_id_ordinal"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    printed_text: str
    printed_law_number: str
    printed_title: str
    printed_bill_number: Optional[str] = None
    first_reading_date: Optional[date] = None
    second_reading_date: Optional[date] = None
    third_reading_date: Optional[date] = None
    commencement_date: Optional[date] = None

    kind: ActHistoryEntryKind
    bill_link_source: Optional[BillLinkSource] = None

    act_id: int = Field(foreign_key="act.id", index=True)
    bill_id: Optional[int] = Field(default=None, foreign_key="bill.id", index=True)
