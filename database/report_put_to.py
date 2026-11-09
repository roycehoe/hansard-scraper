from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.report  # noqa: F401 registers Report so the foreign key resolves
from enums import ReportPutToSource


class ReportPutTo(SQLModel, table=True):
    __tablename__ = "report_put_to"
    __table_args__ = (
        UniqueConstraint(
            "sprs_report_id", "ordinal", name="uq_report_put_to_sprs_report_id_ordinal"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    office_printed: str = Field(index=True)
    printed_text: str
    source: ReportPutToSource
    first_ordinal: int

    sprs_report_id: str = Field(foreign_key="report.report_id", index=True)
