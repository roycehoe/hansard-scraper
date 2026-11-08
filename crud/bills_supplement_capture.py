from dataclasses import dataclass

from sqlmodel import Session, col, func, select

from database.bills_supplement import BillsSupplementCapture


@dataclass(frozen=True)
class BillsSupplementCaptureRow:
    id: int
    capture_url: str


class CRUDBillsSupplementCapture:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, captures: list[BillsSupplementCapture]) -> None:
        self.session.add_all(captures)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(BillsSupplementCapture)
        return self.session.exec(statement).one()

    def get_rows(self) -> list[BillsSupplementCaptureRow]:
        statement = select(
            BillsSupplementCapture.id, BillsSupplementCapture.capture_url
        ).order_by(col(BillsSupplementCapture.id))
        return [
            BillsSupplementCaptureRow(*row)
            for row in self.session.exec(statement).all()
        ]
