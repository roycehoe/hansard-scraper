from pydantic import BaseModel, ConfigDict

from enums import LawLinkVerdict


class LawLinkCheckVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_id: str
    verdict: LawLinkVerdict
    note: str
