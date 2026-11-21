from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import PictureKind


class TypedTable(BaseModel):
    model_config = ConfigDict(frozen=True)

    caption: str
    header_rows: list[list[str]]
    body_rows: list[list[str]]
    notes: list[str]


class TypedCopy(BaseModel):
    model_config = ConfigDict(frozen=True)

    heading: str
    tables: list[TypedTable]
    uncertain: list[str]
    note: str


class PlannedReportPicture(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: int
    picture_index: int
    content_offset: int
    follows_ordinal: Optional[int]
    media_type: str
    sha256: str
    kind: PictureKind
    typed_copy: Optional[TypedCopy]


class ReportPicturePlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    pictures: list[PlannedReportPicture]
