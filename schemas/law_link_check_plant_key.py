from pydantic import BaseModel, ConfigDict

from enums import LawLinkCheckRule


class LawLinkCheckPlant(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    rule: LawLinkCheckRule
    original: str
    planted: str


class LawLinkCheckPlantKey(BaseModel):
    model_config = ConfigDict(frozen=True)

    plants: list[LawLinkCheckPlant]
