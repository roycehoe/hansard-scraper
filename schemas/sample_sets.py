from pydantic import BaseModel, ConfigDict


class SampleSets(BaseModel):
    model_config = ConfigDict(frozen=True)

    pilot: list[int]
    held_out: list[int]
    regression: list[int]
