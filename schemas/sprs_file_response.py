from typing import Optional

from pydantic import BaseModel, ConfigDict


class SprsFileResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    status_code: int
    content_type: Optional[str]
    content_disposition: Optional[str]
    is_body_empty: bool
