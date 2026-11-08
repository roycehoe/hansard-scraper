from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

import database.bill  # noqa: F401 registers Bill so the foreign key resolves
from enums import BillLinkSource, EgazetteSupplementKind


class EgazetteSupplement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    url: str = Field(unique=True)
    year: int
    supplement_kind: EgazetteSupplementKind
    number: int
    file_path: str
    size_bytes: int
    sha256: str
    printed_title: str
    printed_bill_number: str
    bill_number: str
    first_reading_date: date
    passing_date: Optional[date] = None
    printed_act_number: Optional[str] = None

    fetched_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    bill_link_source: Optional[BillLinkSource] = None

    bill_id: Optional[int] = Field(default=None, foreign_key="bill.id", index=True)
