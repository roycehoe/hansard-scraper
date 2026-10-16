from pydantic import BaseModel


class LegislativeAssemblyOverride(BaseModel):
    name: str
    parliament_number: int
    source_is_legislative_assembly: bool
    is_legislative_assembly: bool
    reason: str


class SpeakerOverrides(BaseModel):
    legislative_assembly_overrides: list[LegislativeAssemblyOverride]
