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

    def set_is_legislative_assembly_bulk(self, updates: dict[int, bool]) -> int:
        if not updates:
            return 0
        update_result = self.session.execute(
            text(
                "UPDATE speaker SET is_legislative_assembly = v.is_legislative_assembly "
                "FROM UNNEST(:ids, :is_legislative_assembly_values) AS v(id, is_legislative_assembly) "
                "WHERE speaker.id = v.id"
            ),
            {"ids": list(updates.keys()), "is_legislative_assembly_values": list(updates.values())},
        )
        return update_result.rowcount

    def set_party_bulk(self, updates: dict[int, str]) -> int:
        if not updates:
            return 0
        update_result = self.session.execute(
            text(
                "UPDATE speaker SET party = v.party "
                "FROM UNNEST(:ids, :parties) AS v(id, party) "
                "WHERE speaker.id = v.id"
            ),
            {"ids": list(updates.keys()), "parties": list(updates.values())},
        )
        return update_result.rowcount
