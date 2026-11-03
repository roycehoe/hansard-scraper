from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.speaker  # noqa: F401 registers Speaker so the foreign key resolves
import database.speech  # noqa: F401 registers Report and Speech so the foreign key resolves
from enums import ReportAskerSource


class ReportAsker(SQLModel, table=True):
    __tablename__ = "report_asker"
    __table_args__ = (
        UniqueConstraint(
            "report_id", "ordinal", name="uq_report_asker_report_id_ordinal"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    printed_name: str
    source: ReportAskerSource
    reader_printed_name: Optional[str] = None

    report_id: int = Field(foreign_key="report.id", index=True)
    speaker_id: Optional[int] = Field(
        default=None, foreign_key="speaker.id", index=True
    )
    reader_speaker_id: Optional[int] = Field(default=None, foreign_key="speaker.id")
