from typing import Optional

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

import database.speech  # noqa: F401 registers Report and Speech so the foreign key resolves
from enums import ReportLinkRule, ReportLinkType


class ReportLink(SQLModel, table=True):
    __tablename__ = "report_link"
    __table_args__ = (
        UniqueConstraint(
            "source_report_id",
            "target_report_id",
            "link_type",
            name="uq_report_link_source_target_type",
        ),
        CheckConstraint(
            "source_report_id <> target_report_id",
            name="ck_report_link_source_differs_from_target",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    link_type: ReportLinkType
    rule: ReportLinkRule
    printed_citation: str

    source_report_id: str = Field(foreign_key="report.report_id")
    target_report_id: str = Field(foreign_key="report.report_id", index=True)
