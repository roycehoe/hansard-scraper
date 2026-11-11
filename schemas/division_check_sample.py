from pydantic import BaseModel, ConfigDict

from enums import DivisionCheckPlantKind, DivisionCheckRule


class DivisionCheckCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: DivisionCheckRule
    group: str
    source_text: str
    data_claim: str
    database_key: str


class DivisionCheckPacket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    packet_id: str
    source_text: str
    data_claim: str


class DivisionCheckPlant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    packet_id: str
    kind: DivisionCheckPlantKind


class DivisionCheckKey(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int
    rule: DivisionCheckRule
    plants: list[DivisionCheckPlant]
    packet_id_to_database_key: dict[str, str]
