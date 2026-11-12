from datetime import date, datetime
from typing import Optional

from sqlalchemy import update
from sqlmodel import Session, col, func, select

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

    def get_by_ids(self, minutes_ids: list[int]) -> list[Minutes]:
        statement = (
            select(Minutes)
            .where(col(Minutes.id).in_(minutes_ids))
            .order_by(col(Minutes.id))
            .execution_options(populate_existing=True)
        )
        return list(self.session.exec(statement).all())

    def get_by_sitting_date_from_and_extracted_text_not_null(
        self, sitting_date_from: date
    ) -> list[Minutes]:
        statement = (
            select(Minutes)
            .where(col(Minutes.sitting_date) >= sitting_date_from)
            .where(col(Minutes.extracted_text).is_not(None))
            .order_by(col(Minutes.sitting_date))
        )
        return list(self.session.exec(statement).all())

    def get_by_statuses(self, statuses: list[MinutesStatus]) -> list[Minutes]:
        statement = (
            select(Minutes)
            .where(col(Minutes.status).in_(statuses))
            .order_by(col(Minutes.sitting_date))
        )
        return list(self.session.exec(statement).all())

    def get_min_sitting_date_by_index_source(
        self, index_source: MinutesIndexSource
    ) -> Optional[date]:
        statement = select(func.min(Minutes.sitting_date)).where(
            col(Minutes.index_source) == index_source
        )
        return self.session.exec(statement).one()

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

    def set_status_by_id_and_status(
        self,
        minutes_id: int,
        expected_status: MinutesStatus,
        status: MinutesStatus,
        status_note: Optional[str],
    ) -> None:
        statement = (
            update(Minutes)
            .where(col(Minutes.id) == minutes_id)
            .where(col(Minutes.status) == expected_status)
            .values(status=status, status_note=status_note)
        )
        update_result = self.session.execute(statement)

        if update_result.rowcount != 1:
            raise HansardWriteCheckError(
                f"Minutes {minutes_id} is no longer {expected_status}"
            )

    def set_file_by_id_and_status(
        self,
        minutes_id: int,
        expected_status: MinutesStatus,
        status: MinutesStatus,
        status_note: Optional[str],
        file_format: Optional[MinutesFileFormat],
        archive_timestamp: Optional[str],
        sha256: str,
        size_bytes: int,
        file_bytes: Optional[bytes],
        fetched_at: datetime,
        extracted_text: Optional[str],
    ) -> None:
        statement = (
            update(Minutes)
            .where(col(Minutes.id) == minutes_id)
            .where(col(Minutes.status) == expected_status)
            .values(
                status=status,
                status_note=status_note,
                file_format=file_format,
                archive_timestamp=archive_timestamp,
                sha256=sha256,
                size_bytes=size_bytes,
                file_bytes=file_bytes,
                fetched_at=fetched_at,
                extracted_text=extracted_text,
            )
        )
        update_result = self.session.execute(statement)

        if update_result.rowcount != 1:
            raise HansardWriteCheckError(
                f"Minutes {minutes_id} is no longer {expected_status}"
            )
