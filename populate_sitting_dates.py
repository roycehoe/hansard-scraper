import json

from sqlmodel import Session, select

from database.init import create_db_and_tables, get_session
from database.report import HandsardSittingDateResult, HandsardWebsiteResponse
from gateway.handsard_report import get_handsard_report_response

_LIST_FIELDS = {"footNote", "atbpList", "ptbaList", "attendanceList"}


def _serialize_lists(result: dict) -> dict:
    return {k: (json.dumps(v) if k in _LIST_FIELDS and isinstance(v, list) else v) for k, v in result.items()}


def populate_sitting_dates(session: Session):
    all_sitting_dates = {r.sitting_date for r in session.exec(select(HandsardWebsiteResponse)).all()}
    existing_sitting_dates = {r.sitting_date for r in session.exec(select(HandsardSittingDateResult)).all()}

    dates_to_fetch = list(all_sitting_dates - existing_sitting_dates)
    for i, sitting_date in enumerate(dates_to_fetch, start=1):
        print(f"{i}/{len(dates_to_fetch)}: {sitting_date}")
        result = get_handsard_report_response(sitting_date)
        if not result:
            continue
        session.add(HandsardSittingDateResult(**_serialize_lists(result)))

    session.commit()


if __name__ == "__main__":
    create_db_and_tables()
    session = next(get_session())
    populate_sitting_dates(session)
