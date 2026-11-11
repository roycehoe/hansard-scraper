from dataclasses import dataclass
from datetime import date

from sqlalchemy import update
from sqlmodel import Session, col, delete, select

from database.division import Division
from enums import DivisionCountSource, DivisionListStatus
from utils.division_detachment import DivisionDetachment
from utils.division_update import DivisionUpdate


@dataclass(frozen=True)
class DivisionListStatusRow:
    sitting_date: date
    list_status: DivisionListStatus


class CRUDDivision:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, divisions: list[Division]) -> None:
        self.session.add_all(divisions)
        self.session.flush()

    def get_by_sprs_report_ids(self, sprs_report_ids: list[str]) -> list[Division]:
        statement = (
            select(Division)
            .where(col(Division.sprs_report_id).in_(sprs_report_ids))
            .order_by(
                col(Division.sprs_report_id), col(Division.report_division_number)
            )
        )
        return list(self.session.exec(statement).all())

    def get_by_ids(self, division_ids: list[int]) -> list[Division]:
        statement = (
            select(Division)
            .where(col(Division.id).in_(division_ids))
            .order_by(col(Division.id))
        )
        return list(self.session.exec(statement).all())

    def get_by_sitting_dates_and_sprs_report_id_not_null(
        self, sitting_dates: list[date]
    ) -> list[Division]:
        statement = (
            select(Division)
            .where(col(Division.sitting_date).in_(sitting_dates))
            .where(col(Division.sprs_report_id).is_not(None))
            .order_by(col(Division.sitting_date), col(Division.id))
        )
        return list(self.session.exec(statement).all())

    def get_by_sitting_dates(self, sitting_dates: list[date]) -> list[Division]:
        statement = (
            select(Division)
            .where(col(Division.sitting_date).in_(sitting_dates))
            .order_by(col(Division.sitting_date), col(Division.id))
        )
        return list(self.session.exec(statement).all())

    def get_by_count_source(self, count_source: DivisionCountSource) -> list[Division]:
        statement = (
            select(Division)
            .where(col(Division.count_source) == count_source)
            .order_by(col(Division.sitting_date), col(Division.id))
        )
        return list(self.session.exec(statement).all())

    def get_by_list_statuses(
        self, list_statuses: list[DivisionListStatus]
    ) -> list[Division]:
        statement = (
            select(Division)
            .where(col(Division.list_status).in_(list_statuses))
            .order_by(col(Division.sitting_date), col(Division.id))
        )
        return list(self.session.exec(statement).all())

    def get_list_status_rows_by_sprs_report_id_not_null(
        self,
    ) -> list[DivisionListStatusRow]:
        statement = select(Division.sitting_date, Division.list_status).where(
            col(Division.sprs_report_id).is_not(None)
        )
        return [
            DivisionListStatusRow(*row) for row in self.session.exec(statement).all()
        ]

    def delete_by_ids(self, division_ids: list[int]) -> int:
        statement = delete(Division).where(col(Division.id).in_(division_ids))

        return self.session.exec(statement).rowcount

    def update_many(self, division_updates: list[DivisionUpdate]) -> None:
        if not division_updates:
            return

        self.session.execute(
            update(Division),
            [
                {
                    "id": division_update.id,
                    "sitting_date": division_update.sitting_date,
                    "parliament_number": division_update.parliament_number,
                    "report_division_number": division_update.report_division_number,
                    "speech_ordinal": division_update.speech_ordinal,
                    "count_source": division_update.count_source,
                    "printed_counts": division_update.printed_counts,
                    "ayes": division_update.ayes,
                    "noes": division_update.noes,
                    "abstentions": division_update.abstentions,
                    "absent": division_update.absent,
                    "paired": division_update.paired,
                    "list_status": division_update.list_status,
                    "printed_list": division_update.printed_list,
                }
                for division_update in division_updates
            ],
        )

    def detach_report_many(self, division_detachments: list[DivisionDetachment]) -> int:
        detached_count = 0
        for division_detachment in division_detachments:
            statement = (
                update(Division)
                .where(col(Division.id) == division_detachment.division_id)
                .values(
                    sprs_report_id=None,
                    report_division_number=None,
                    speech_ordinal=None,
                    count_source=DivisionCountSource.MINUTES,
                    printed_counts=division_detachment.printed_counts,
                    ayes=division_detachment.ayes,
                    noes=division_detachment.noes,
                    abstentions=division_detachment.abstentions,
                    absent=None,
                    paired=None,
                    list_status=DivisionListStatus.NOT_PRINTED,
                    printed_list=None,
                )
            )
            detached_count += self.session.execute(statement).rowcount

        return detached_count
