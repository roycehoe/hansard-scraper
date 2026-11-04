from typing import Optional

from pydantic import BaseModel, ConfigDict


class PqRolesRoundOneRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    report_id: int
    role: Optional[str] = None
    speaker_id: Optional[int] = None
    printed_name: Optional[str] = None
    state: Optional[str] = None
    answerer_rank: Optional[int] = None
