from sqlmodel import Session

from crud.leave_period_printing import CRUDLeavePeriodPrinting
from crud.sitting import CRUDSitting
from database.init import build_read_only_engine
from exceptions import HansardLeaveSectionCheckError
from logs import logger
from services.leave_section import get_leave_section_wordings
from settings import settings
from utils.sitting_dates import parse_sitting_date

_READ_ISOLATION_LEVEL = "REPEATABLE READ"
_SITTING_BATCH = 20


def check_leave_sections() -> None:
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_READ_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        sitting_ids_with_printings = set(
            CRUDLeavePeriodPrinting(session).get_distinct_sitting_ids()
        )
        sitting_id_to_sitting_date = {
            sitting_date_row.id: parse_sitting_date(sitting_date_row.sitting_date)
            for sitting_date_row in CRUDSitting(session).get_date_rows()
        }
        sitting_ids_to_read = sorted(
            sitting_id
            for sitting_id in sitting_id_to_sitting_date
            if sitting_id not in sitting_ids_with_printings
        )
        unread_sittings = []
        for start in range(0, len(sitting_ids_to_read), _SITTING_BATCH):
            for sitting_leave_text_row in CRUDSitting(
                session
            ).get_leave_text_rows_by_ids(
                sitting_ids_to_read[start : start + _SITTING_BATCH]
            ):
                if sitting_leave_text_row.markdown_content is None:
                    continue
                leave_section_wordings = get_leave_section_wordings(
                    sitting_leave_text_row.markdown_content
                )
                if leave_section_wordings:
                    unread_sittings.append(
                        (
                            sitting_id_to_sitting_date[sitting_leave_text_row.id],
                            sitting_leave_text_row.id,
                            leave_section_wordings,
                        )
                    )
    for sitting_date, sitting_id, leave_section_wordings in sorted(unread_sittings):
        logger.info(
            f"Sitting {sitting_id} of {sitting_date.date()} prints"
            f" {', '.join(leave_section_wordings)} and holds no leave period printing"
        )
    if unread_sittings:
        raise HansardLeaveSectionCheckError(
            f"{len(unread_sittings)} sittings print a leave section or a granting sentence and hold no leave period printing"
        )
    logger.info(
        "Every sitting that prints a leave section holds a leave period printing"
    )


if __name__ == "__main__":
    check_leave_sections()
