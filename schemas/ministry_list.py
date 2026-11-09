from pydantic import BaseModel, ConfigDict, Field, RootModel


class MinistryNames(RootModel[list[str]]):
    model_config = ConfigDict(frozen=True)


class OfficeTitleMinistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    office_printed: str
    ministry_names: list[str]
    reason: str


class OfficeTitleMinistryEntries(RootModel[list[OfficeTitleMinistryEntry]]):
    model_config = ConfigDict(frozen=True)


class MinistrySeeAlsoEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ministry_name: str
    see_also_ministry_name: str
    note: str
    source_url: str = Field(pattern=r"^https://")


class MinistrySeeAlsoEntries(RootModel[list[MinistrySeeAlsoEntry]]):
    model_config = ConfigDict(frozen=True)
