from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.speaker  # noqa: F401 registers Speaker so the foreign key resolves
import database.speech  # noqa: F401 registers Report and Speech so the foreign key resolves
from enums import OfficeClass, OfficeSource, ParticipantRole, ParticipantRoleSource


class ReportParticipant(SQLModel, table=True):
    __tablename__ = "report_participant"
    __table_args__ = (
        UniqueConstraint(
            "report_id", "ordinal", name="uq_report_participant_report_id_ordinal"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    role: ParticipantRole
    role_source: ParticipantRoleSource
    first_ordinal: int
    printed_name: str
    answering_for_printed: Optional[str] = None
    office_printed: Optional[str] = None
    office_class: Optional[OfficeClass] = None
    office_source: Optional[OfficeSource] = None

    report_id: int = Field(foreign_key="report.id", index=True)
    speaker_id: Optional[int] = Field(
        default=None, foreign_key="speaker.id", index=True
    )
