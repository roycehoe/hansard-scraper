from pydantic import BaseModel, ConfigDict


class EgazetteSupplementResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    status_code: int
    content: bytes
