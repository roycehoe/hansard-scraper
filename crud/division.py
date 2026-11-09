from datetime import date

from sqlalchemy import update
from sqlmodel import Session, col, delete, select

from database.division import Division
from utils.division_update import DivisionUpdate


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
