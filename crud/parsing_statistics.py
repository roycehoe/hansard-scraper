from sqlmodel import Session

from database.report import ParsingStatistics


class CRUDParsingStatistics:
    def __init__(self, session: Session):
        self.session = session

    def create(self, statistics: ParsingStatistics) -> None:
        self.session.add(statistics)
        self.session.commit()
