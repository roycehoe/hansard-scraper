from pydantic import BaseModel, ConfigDict

from enums import HandCheckPlantKind


class HandCheckPlant(BaseModel):
    model_config = ConfigDict(frozen=True)

    speech_id: int
    kind: HandCheckPlantKind
    original: str
    planted: str


class HandCheckPlantKey(BaseModel):
    model_config = ConfigDict(frozen=True)

    round_number: int
    plants: list[HandCheckPlant]
