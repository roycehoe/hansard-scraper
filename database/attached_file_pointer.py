from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.attached_file  # noqa: F401 registers AttachedFile so the foreign key resolves
import database.speech  # noqa: F401 registers Report so the foreign key resolves
from enums import AttachedFilePointerShape, ParagraphTieRule


class AttachedFilePointer(SQLModel, table=True):
    __tablename__ = "attached_file_pointer"
    __table_args__ = (
        UniqueConstraint(
            "sprs_report_id",
            "ordinal",
            name="uq_attached_file_pointer_sprs_report_id_ordinal",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    printed_text: str
    href: str
    shape: AttachedFilePointerShape
    download_value: Optional[str] = None
    speech_ordinal: Optional[int] = None
    paragraph_tie_rule: Optional[ParagraphTieRule] = None

    sprs_report_id: str = Field(foreign_key="report.report_id", index=True)
    attached_file_id: Optional[int] = Field(
        default=None, foreign_key="attached_file.id", index=True
    )
