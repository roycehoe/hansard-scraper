from typing import Optional

from pydantic import BaseModel, ConfigDict


class MinutesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    status_code: int
    content: bytes
    waf_action: Optional[str] = None
    cache_status: Optional[str] = None
