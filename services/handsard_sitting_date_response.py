import json
from typing import Optional

from database.handsard_sitting_date_response import HandsardSittingDateResponse

_LIST_FIELDS = {"footNote", "atbpList", "ptbaList", "attendanceList"}


def _serialize_lists(result: dict) -> dict:
    return {k: (json.dumps(v) if k in _LIST_FIELDS and isinstance(v, list) else v) for k, v in result.items()}


def build_handsard_sitting_date_response(result: dict) -> Optional[HandsardSittingDateResponse]:
    return HandsardSittingDateResponse(**_serialize_lists(result))
