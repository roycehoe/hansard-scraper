from sqlmodel import Session

from database.report import ParsingStatistics


class CRUDParsingStatistics:
    def __init__(self, session: Session):
        self.session = session

    def create_many(self, statistics: list[ParsingStatistics]) -> None:
        self.session.bulk_insert_mappings(ParsingStatistics, statistics)
        self.session.commit()
