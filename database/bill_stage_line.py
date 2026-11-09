from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.report  # noqa: F401 registers Report so the foreign key resolves
from enums import BillStage


class BillStageLine(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "sprs_report_id",
            "ordinal",
            "stage",
            name="uq_billstageline_sprs_report_id_ordinal_stage",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    stage: BillStage
    printed_text: str
    ordinal: int

    sprs_report_id: str = Field(foreign_key="report.report_id", index=True)
