from dataclasses import dataclass

from sqlmodel import Session, delete, select

from database.office_title_ministry import OfficeTitleMinistry
from enums import OfficeTitleMinistrySource


@dataclass(frozen=True)
class OfficeTitleMinistryRow:
    id: int
    office_printed: str
    ordinal: int
    source: OfficeTitleMinistrySource
    ministry_id: int


class CRUDOfficeTitleMinistry:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, office_title_ministries: list[OfficeTitleMinistry]) -> None:
        self.session.add_all(office_title_ministries)
        self.session.flush()

    def get_rows(self) -> list[OfficeTitleMinistryRow]:
        statement = select(
            OfficeTitleMinistry.id,
            OfficeTitleMinistry.office_printed,
            OfficeTitleMinistry.ordinal,
            OfficeTitleMinistry.source,
            OfficeTitleMinistry.ministry_id,
        ).order_by(OfficeTitleMinistry.id)
        return [
            OfficeTitleMinistryRow(*row) for row in self.session.exec(statement).all()
        ]

    def get_distinct_office_printed(self) -> list[str]:
        statement = (
            select(OfficeTitleMinistry.office_printed)
            .distinct()
            .order_by(OfficeTitleMinistry.office_printed)
        )
        return list(self.session.exec(statement).all())

    def delete_all(self) -> int:
        statement = delete(OfficeTitleMinistry)

        return self.session.exec(statement).rowcount
