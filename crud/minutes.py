from datetime import date
from typing import Optional

from sqlalchemy import update
from sqlmodel import Session, col, select

from database.minutes import Minutes
from enums import MinutesFileFormat, MinutesIndexSource, MinutesStatus
from exceptions import HansardWriteCheckError


class CRUDMinutes:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, minutes_rows: list[Minutes]) -> None:
        self.session.add_all(minutes_rows)
        self.session.flush()

    def get_by_sitting_dates(self, sitting_dates: list[date]) -> list[Minutes]:
        statement = (
            select(Minutes)
            .where(col(Minutes.sitting_date).in_(sitting_dates))
            .order_by(col(Minutes.sitting_date))
        )
        return list(self.session.exec(statement).all())

    def set_listed_by_id_and_status(
        self,
        minutes_id: int,
        expected_status: MinutesStatus,
        index_source: MinutesIndexSource,
        index_capture_id: Optional[int],
        printed_label: Optional[str],
        printed_parliament: Optional[str],
        file_url: str,
        file_format: MinutesFileFormat,
    ) -> None:
        statement = (
            update(Minutes)
            .where(col(Minutes.id) == minutes_id)
            .where(col(Minutes.status) == expected_status)
            .values(
                status=MinutesStatus.LISTED,
                index_source=index_source,
                index_capture_id=index_capture_id,
                printed_label=printed_label,
                printed_parliament=printed_parliament,
                file_url=file_url,
                file_format=file_format,
                status_note=None,
            )
        )
        update_result = self.session.execute(statement)

        if update_result.rowcount != 1:
            raise HansardWriteCheckError(
                f"Minutes {minutes_id} is no longer {expected_status}"
            )
