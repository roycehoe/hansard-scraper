from sqlmodel import Session, select

from database.report import Report


class CRUDReport:
    def __init__(self, session: Session):
        self.session = session

    def create(self, report: Report) -> None:
        self.session.add(report)
        self.session.commit()

    def get_all(self) -> list[Report]:
        return list(self.session.exec(select(Report)).all())
