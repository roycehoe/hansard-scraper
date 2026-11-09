from typing import Optional

from pydantic import BaseModel, ConfigDict


class LeaveSeatCheckPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str
    source_text: str
    data_says: str
    rule: str


class LeaveSeatCheckKeyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str
    group: str
    table_name: str
    row_id: int
    is_plant: bool
    plant_note: Optional[str]
