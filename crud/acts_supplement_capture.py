from dataclasses import dataclass

from sqlmodel import Session, col, func, select

from database.acts_supplement import ActsSupplementCapture


@dataclass(frozen=True)
class ActsSupplementCaptureRow:
    id: int
    capture_url: str


class CRUDActsSupplementCapture:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, captures: list[ActsSupplementCapture]) -> None:
        self.session.add_all(captures)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(ActsSupplementCapture)
        return self.session.exec(statement).one()

    def get_rows(self) -> list[ActsSupplementCaptureRow]:
        statement = select(
            ActsSupplementCapture.id, ActsSupplementCapture.capture_url
        ).order_by(col(ActsSupplementCapture.id))
        return [
            ActsSupplementCaptureRow(*row) for row in self.session.exec(statement).all()
        ]
