from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.sitting  # noqa: F401 registers Sitting so the foreign key resolves
from enums import AttachedFileKind


class AttachedFile(SQLModel, table=True):
    __tablename__ = "attached_file"
    __table_args__ = (
        UniqueConstraint(
            "sitting_id",
            "kind",
            "sprs_file_id",
            name="uq_attached_file_sitting_id_kind_sprs_file_id",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    kind: AttachedFileKind
    sprs_file_id: int
    printed_title: str
    printed_file_path: str
    file_name: str
    section_type: Optional[str] = None
    download_value: Optional[str] = None

    sitting_id: int = Field(foreign_key="sitting.id", index=True)
