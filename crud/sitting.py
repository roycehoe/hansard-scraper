from typing import Optional

from sqlmodel import Session, select

from database.sitting import Sitting


class CRUDSitting:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sitting: Sitting) -> None:
        self.session.add(sitting)
        self.session.commit()

    def get_all(self) -> list[Sitting]:
        return list(self.session.exec(select(Sitting)).all())

    def get_parliament_columns(self) -> list[tuple[int, Optional[int], Optional[int]]]:
        """Returns (id, parlement_no, volume_no) for every sitting — no large text columns."""
        rows = self.session.exec(
            select(Sitting.id, Sitting.parlement_no, Sitting.volume_no)
        ).all()
        return [(row[0], row[1], row[2]) for row in rows if row[0] is not None]

    def get_all_sitting_dates(self) -> set[str]:
        rows = self.session.exec(select(Sitting.sitting_date)).all()
        return {r for r in rows if r is not None}
