from pydantic import BaseModel, ConfigDict


class LegislativeAssemblyOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    parliament_number: int
    source_is_legislative_assembly: bool
    is_legislative_assembly: bool
    reason: str


class PartyOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    parliament_number: int
    source_party: str
    party: str
    reason: str


class SpeakerOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    legislative_assembly_overrides: list[LegislativeAssemblyOverride]
    party_overrides: list[PartyOverride]
