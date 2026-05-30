import json

from sqlmodel import Session

from crud.handsard_sitting_date_response import CRUDHandsardSittingDateResponse
from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from database.report import HandsardSittingDateResponse
from gateway.handsard_report import get_handsard_report_response

_LIST_FIELDS = {"footNote", "atbpList", "ptbaList", "attendanceList"}


def _prepare_value(k: str, v) -> object:
    if k in _LIST_FIELDS and isinstance(v, list):
        return json.dumps(v)
    if isinstance(v, str):
        return v.replace("\x00", "")
    return v


def _serialize_lists(result: dict) -> dict:
    return {k: _prepare_value(k, v) for k, v in result.items()}


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
        crud.create_many([HandsardSittingDateResponse(**_serialize_lists(result))])
