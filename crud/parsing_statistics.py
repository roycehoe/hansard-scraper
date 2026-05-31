from sqlmodel import Session, select

from database.parsing_statistics import ParsingStatistics


class CRUDParsingStatistics:
    def __init__(self, session: Session):
        self.session = session

    def create(self, statistics: ParsingStatistics) -> None:
        self.session.add(statistics)
        self.session.commit()

    def create_many(self, statistics: list[ParsingStatistics]) -> None:
        self.session.add_all(statistics)
        self.session.commit()

    def get_all(self) -> list[ParsingStatistics]:
        return list(self.session.exec(select(ParsingStatistics)).all())

    def get_all_report_ids(self) -> set[str]:
        return set(self.session.exec(select(ParsingStatistics.report_id)).all()) - {None}
