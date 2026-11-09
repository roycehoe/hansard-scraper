from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.report  # noqa: F401 registers Report so the foreign key resolves
import database.speaker  # noqa: F401 registers Speaker so the foreign key resolves


class BillReportSpeaker(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "sprs_report_id",
            "speaker_id",
            name="uq_billreportspeaker_sprs_report_id_speaker_id",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    speech_count: int
    first_ordinal: int
    printed_speaker: str

    sprs_report_id: str = Field(foreign_key="report.report_id", index=True)
    speaker_id: int = Field(foreign_key="speaker.id", index=True)
