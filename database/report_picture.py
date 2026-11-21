from typing import Optional

from sqlalchemy import Column, LargeBinary, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

import database.report  # noqa: F401 registers Report so the foreign key resolves
from enums import PictureKind


class ReportPicture(SQLModel, table=True):
    __tablename__ = "report_picture"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "picture_index",
            name="uq_report_picture_report_id_picture_index",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    kind: PictureKind
    picture_index: int
    content_offset: int
    follows_ordinal: Optional[int] = None
    media_type: str
    size_bytes: int
    sha256: str = Field(index=True)
    picture_bytes: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    typed_copy: Optional[dict[str, object]] = Field(
        default=None, sa_column=Column(JSONB(none_as_null=True), nullable=True)
    )

    report_id: int = Field(foreign_key="report.id", index=True)
