from pydantic import BaseModel, ConfigDict, RootModel

from enums import OfficeCheckRule, OfficeCheckVerdictKind


class OfficeCheckPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str
    rule: OfficeCheckRule
    group: str
    source_text: str
    data_says: str
    made_by: str
    row_key: str


class OfficeCheckPackets(RootModel[list[OfficeCheckPacket]]):
    model_config = ConfigDict(frozen=True)


class OfficeCheckPlantKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: OfficeCheckRule
    round_number: int
    seed: int
    planted_packet_ids: list[str]


class OfficeCheckVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str
    verdict: OfficeCheckVerdictKind
    note: str


class OfficeCheckFlag(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str
    rule: OfficeCheckRule
    group: str
    source_text: str
    data_says: str
    made_by: str
    row_key: str
    sonnet_verdict: OfficeCheckVerdictKind
    opus_verdict: OfficeCheckVerdictKind
    sonnet_note: str
    opus_note: str


class OfficeCheckFlags(RootModel[list[OfficeCheckFlag]]):
    model_config = ConfigDict(frozen=True)
