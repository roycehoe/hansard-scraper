from typing import Optional

from pydantic import BaseModel


class MpResult(BaseModel):
    name: str
    party: str
    is_legislative_assembly: bool
    parliament_number: int
    comments: Optional[str] = None
