from pydantic import BaseModel, ConfigDict

from schemas.hansard_search_result import HansardSearchResult


class FetchedHit(BaseModel):
    model_config = ConfigDict(frozen=True)

    search_result: HansardSearchResult
    content: str
    speech_count: int


class FetchedReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    content: str
    speech_count: int


class CoverageRefillPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    fetched_hits: list[FetchedHit]
    fetched_reports: list[FetchedReport]
