from dataclasses import dataclass

from sqlmodel import Session, col, func, select

from database.repealed_acts import RepealedActsCapture


@dataclass(frozen=True)
class RepealedActsCaptureRow:
    id: int
    capture_url: str


class CRUDRepealedActsCapture:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, captures: list[RepealedActsCapture]) -> None:
        self.session.add_all(captures)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(RepealedActsCapture)
        return self.session.exec(statement).one()

    def get_rows(self) -> list[RepealedActsCaptureRow]:
        statement = select(
            RepealedActsCapture.id, RepealedActsCapture.capture_url
        ).order_by(col(RepealedActsCapture.id))
        return [
            RepealedActsCaptureRow(*row) for row in self.session.exec(statement).all()
        ]
