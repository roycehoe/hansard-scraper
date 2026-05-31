from database.mp import Mp
from schemas.mp import MpResult


def build_mp(result: MpResult) -> Mp:
    return Mp(**result.model_dump())
