from pydantic import BaseModel, ConfigDict, RootModel

from enums import LawLinkCheckRule


class LawLinkCheckPacket(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    rule: LawLinkCheckRule
    group: str
    row_id: int
    source_text: str
    data_says: str
    rule_text: str


class LawLinkCheckPackets(RootModel[list[LawLinkCheckPacket]]):
    model_config = ConfigDict(frozen=True)
