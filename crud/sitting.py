from sqlmodel import Session, col, select

from database.sitting import Sitting


class CRUDSitting:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sitting: Sitting) -> None:
        self.session.add(sitting)
        self.session.commit()

    def create_many(self, sittings: list[Sitting]) -> None:
        self.session.add_all(sittings)
        self.session.commit()

    def get_all(self) -> list[Sitting]:
        return list(self.session.exec(select(Sitting)).all())

    def get_all_sitting_dates(self) -> set[str]:
        sitting_dates = self.session.exec(select(Sitting.sitting_date)).all()
        return {sitting_date for sitting_date in sitting_dates if sitting_date is not None}

    def get_markdown_by_dates(self, dates: list[str]) -> dict[str, str]:
        """Sitting markdown by sitting_date text ("d-m-yyyy"); sittings without markdown are omitted."""
        sitting_markdown_rows = self.session.exec(
            select(Sitting.sitting_date, Sitting.markdown_content).where(
                col(Sitting.sitting_date).in_(dates), Sitting.markdown_content.is_not(None)
            )
        ).all()
        return {sitting_date: markdown for sitting_date, markdown in sitting_markdown_rows}
