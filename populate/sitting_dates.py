import json

from sqlmodel import Session

from crud.handsard_sitting_date_response import CRUDHandsardSittingDateResponse
from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from database.handsard_sitting_date_response import HandsardSittingDateResponse
from gateway.handsard_report import get_handsard_report_response

_LIST_FIELDS = {"footNote", "atbpList", "ptbaList", "attendanceList"}


def _serialize_lists(result: dict) -> dict:
    return {k: (json.dumps(v) if k in _LIST_FIELDS and isinstance(v, list) else v) for k, v in result.items()}


def populate_sitting_dates(session: Session):
    all_sitting_dates = CRUDHandsardWebsiteResponse(session).get_all_sitting_dates()
    existing_sitting_dates = CRUDHandsardSittingDateResponse(session).get_all_sitting_dates()

    dates_to_fetch = list(all_sitting_dates - existing_sitting_dates)
    crud = CRUDHandsardSittingDateResponse(session)
    for i, sitting_date in enumerate(dates_to_fetch, start=1):
        print(f"{i}/{len(dates_to_fetch)}: {sitting_date}")
        result = get_handsard_report_response(sitting_date)
        if not result:
            continue
        crud.create(HandsardSittingDateResponse(**_serialize_lists(result)))
