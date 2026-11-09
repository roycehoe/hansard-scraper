from pydantic import BaseModel, ConfigDict, RootModel

from enums import LawLinkCheckRule
from schemas.law_link_check_verdict import LawLinkCheckVerdict


class LawLinkCheckFlag(BaseModel):
    model_config = ConfigDict(frozen=True)

    packet_id: str
    rule: LawLinkCheckRule
    group: str
    row_id: int
    source_text: str
    data_says: str
    rule_text: str
    sonnet_verdict: LawLinkCheckVerdict
    opus_verdict: LawLinkCheckVerdict


class LawLinkCheckFlags(RootModel[list[LawLinkCheckFlag]]):
    model_config = ConfigDict(frozen=True)
