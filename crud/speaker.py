from sqlalchemy import text
from sqlmodel import Session, select

from database.speaker import Speaker


class CRUDSpeaker:
    def __init__(self, session: Session):
        self.session = session

    def create(self, speaker: Speaker) -> None:
        self.session.add(speaker)
        self.session.commit()

    def update(self, speaker: Speaker) -> None:
        self.session.add(speaker)
        self.session.commit()

    def get_all(self) -> list[Speaker]:
        statement = select(Speaker)
        return list(self.session.exec(statement).all())

    def set_person_ids_bulk(self, updates: dict[int, int]) -> None:
        if not updates:
            return
        self.session.execute(
            text(
                "UPDATE speaker SET person_id = v.person_id "
                "FROM UNNEST(:ids, :person_ids) AS v(id, person_id) "
                "WHERE speaker.id = v.id"
            ),
            {"ids": list(updates.keys()), "person_ids": list(updates.values())},
        )
