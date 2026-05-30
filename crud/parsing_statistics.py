from sqlmodel import Session, select

from database.parsing_statistics import ParsingStatistics


class CRUDParsingStatistics:
    def __init__(self, session: Session):
        self.session = session

    def create(self, statistics: ParsingStatistics) -> None:
        self.session.add(statistics)
        self.session.commit()

    def get_all(self) -> list[ParsingStatistics]:
        return list(self.session.exec(select(ParsingStatistics)).all())
