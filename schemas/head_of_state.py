from typing import Optional

from pydantic import BaseModel


class HeadOfStateResult(BaseModel):
    name: str
    parliament_number: int
    comments: Optional[str] = None
