from dataclasses import dataclass

from sqlmodel import Session, col, func, select

from database.minutes import MinutesIndexCapture


@dataclass(frozen=True)
class MinutesIndexCaptureRow:
    id: int
    capture_url: str


class CRUDMinutesIndexCapture:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, minutes_index_captures: list[MinutesIndexCapture]) -> None:
        self.session.add_all(minutes_index_captures)
        self.session.flush()

    def get_by_capture_urls(
        self, capture_urls: list[str]
    ) -> list[MinutesIndexCaptureRow]:
        statement = (
            select(MinutesIndexCapture.id, MinutesIndexCapture.capture_url)
            .where(col(MinutesIndexCapture.capture_url).in_(capture_urls))
            .order_by(col(MinutesIndexCapture.id))
        )
        return [
            MinutesIndexCaptureRow(*row) for row in self.session.exec(statement).all()
        ]

    def get_count(self) -> int:
        statement = select(func.count()).select_from(MinutesIndexCapture)
        return self.session.exec(statement).one()
