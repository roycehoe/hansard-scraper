from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, RootModel

LIST_PATH_MARKER = "solr_files/"


class HansardAnnexureEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    annexure_id: int = Field(alias="annexureID")
    annexure_title: str = Field(alias="annexureTitle")
    file_path: str = Field(alias="filePath", pattern=LIST_PATH_MARKER)
    file_name: str = Field(alias="fileName")
    # NOTE: a default on a response schema, so an entry without this key cannot halt the daily job
    section_type: Optional[str] = Field(default=None, alias="sectionType")


class HansardAnnexureEntries(RootModel[list[HansardAnnexureEntry]]):
    model_config = ConfigDict(frozen=True)


class HansardVernacularEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    vernacular_id: int = Field(alias="vernacularID")
    vernacular_title: str = Field(alias="vernacularTitle")
    file_path: str = Field(alias="filePath", pattern=LIST_PATH_MARKER)
    file_name: str = Field(alias="fileName")


class HansardVernacularEntries(RootModel[list[HansardVernacularEntry]]):
    model_config = ConfigDict(frozen=True)
