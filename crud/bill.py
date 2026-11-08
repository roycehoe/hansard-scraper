from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import sqlalchemy
from sqlalchemy import update
from sqlmodel import Session, col, delete, func, select

from database.bill import Bill
from enums import ActNumberSource, BillClass, BillNumberSource, RepealedActUrlSource
from utils.act_link_update import BillUpdate


@dataclass(frozen=True)
class BillRow:
    id: int
    title: str
    title_key: str
    first_sitting_date: datetime
    last_sitting_date: datetime
    is_passed: bool
    bill_number: Optional[str]
    bill_number_source: Optional[BillNumberSource]
    bill_class: Optional[BillClass]
    act_number: Optional[str]
    act_number_source: Optional[ActNumberSource]
    repealed_act_url: Optional[str]
    repealed_act_url_source: Optional[RepealedActUrlSource]


class CRUDBill:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, bills: list[Bill]) -> None:
        self.session.add_all(bills)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(Bill)
        return self.session.exec(statement).one()

    def get_count_by_is_passed(self, is_passed: bool) -> int:
        statement = (
            select(func.count())
            .select_from(Bill)
            .where(col(Bill.is_passed).is_(is_passed))
        )
        return self.session.exec(statement).one()

    def get_count_by_bill_number_not_null(self) -> int:
        statement = (
            select(func.count())
            .select_from(Bill)
            .where(col(Bill.bill_number).is_not(None))
        )
        return self.session.exec(statement).one()

    def get_count_by_bill_class_not_null(self) -> int:
        statement = (
            select(func.count())
            .select_from(Bill)
            .where(col(Bill.bill_class).is_not(None))
        )
        return self.session.exec(statement).one()

    def get_count_by_act_number_not_null(self) -> int:
        statement = (
            select(func.count())
            .select_from(Bill)
            .where(col(Bill.act_number).is_not(None))
        )
        return self.session.exec(statement).one()

    def get_count_by_repealed_act_url_not_null(self) -> int:
        statement = (
            select(func.count())
            .select_from(Bill)
            .where(col(Bill.repealed_act_url).is_not(None))
        )
        return self.session.exec(statement).one()

    def get_rows(self) -> list[BillRow]:
        statement = sqlalchemy.select(
            col(Bill.id),
            col(Bill.title),
            col(Bill.title_key),
            col(Bill.first_sitting_date),
            col(Bill.last_sitting_date),
            col(Bill.is_passed),
            col(Bill.bill_number),
            col(Bill.bill_number_source),
            col(Bill.bill_class),
            col(Bill.act_number),
            col(Bill.act_number_source),
            col(Bill.repealed_act_url),
            col(Bill.repealed_act_url_source),
        ).order_by(col(Bill.id))
        return [BillRow(*row) for row in self.session.execute(statement).all()]

    def update_many(self, bill_updates: list[BillUpdate]) -> None:
        if not bill_updates:
            return

        self.session.execute(
            update(Bill),
            [
                {
                    "id": bill_update.id,
                    "title": bill_update.title,
                    "title_key": bill_update.title_key,
                    "first_sitting_date": bill_update.first_sitting_date,
                    "last_sitting_date": bill_update.last_sitting_date,
                    "is_passed": bill_update.is_passed,
                    "bill_number": bill_update.bill_number,
                    "bill_number_source": bill_update.bill_number_source,
                    "bill_class": bill_update.bill_class,
                    "act_number": bill_update.act_number,
                    "act_number_source": bill_update.act_number_source,
                    "repealed_act_url": bill_update.repealed_act_url,
                    "repealed_act_url_source": bill_update.repealed_act_url_source,
                }
                for bill_update in bill_updates
            ],
        )

    def delete_by_ids(self, bill_ids: list[int]) -> None:
        if not bill_ids:
            return

        statement = delete(Bill).where(col(Bill.id).in_(bill_ids))
        self.session.execute(statement)
