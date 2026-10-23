from sqlalchemy import text
from sqlmodel import Session, select

from database.speaker import Speaker


class CRUDSpeaker:
    def __init__(self, session: Session):
        self.session = session

    def create(self, speaker: Speaker) -> None:
        self.session.add(speaker)
        self.session.commit()

    def create_many(self, speakers: list[Speaker]) -> None:
        self.session.add_all(speakers)
        self.session.flush()

    def get_all(self) -> list[Speaker]:
        statement = select(Speaker)
        return list(self.session.exec(statement).all())

    def set_person_ids_bulk(self, speaker_id_to_person_id: dict[int, int]) -> None:
        if not speaker_id_to_person_id:
            return

        self.session.execute(
            text(
                "UPDATE speaker SET person_id = v.person_id "
                "FROM UNNEST(:ids, :person_ids) AS v(id, person_id) "
                "WHERE speaker.id = v.id"
            ),
            {"ids": list(speaker_id_to_person_id.keys()), "person_ids": list(speaker_id_to_person_id.values())},
        )

    def set_is_legislative_assembly_bulk(self, speaker_id_to_is_legislative_assembly: dict[int, bool]) -> int:
        if not speaker_id_to_is_legislative_assembly:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE speaker SET is_legislative_assembly = v.is_legislative_assembly "
                "FROM UNNEST(:ids, :is_legislative_assembly_values) AS v(id, is_legislative_assembly) "
                "WHERE speaker.id = v.id"
            ),
            {"ids": list(speaker_id_to_is_legislative_assembly.keys()), "is_legislative_assembly_values": list(speaker_id_to_is_legislative_assembly.values())},
        )

        return update_result.rowcount

    def set_is_member_bulk(self, speaker_id_to_is_member: dict[int, bool]) -> int:
        if not speaker_id_to_is_member:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE speaker SET is_member = v.is_member "
                "FROM UNNEST(:ids, :is_member_values) AS v(id, is_member) "
                "WHERE speaker.id = v.id"
            ),
            {"ids": list(speaker_id_to_is_member.keys()), "is_member_values": list(speaker_id_to_is_member.values())},
        )

        return update_result.rowcount

    def set_party_bulk(self, speaker_id_to_party: dict[int, str]) -> int:
        if not speaker_id_to_party:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE speaker SET party = v.party "
                "FROM UNNEST(:ids, :parties) AS v(id, party) "
                "WHERE speaker.id = v.id"
            ),
            {"ids": list(speaker_id_to_party.keys()), "parties": list(speaker_id_to_party.values())},
        )

        return update_result.rowcount

    def set_parliament_numbers_bulk(self, speaker_id_to_parliament_number: dict[int, int]) -> int:
        if not speaker_id_to_parliament_number:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE speaker SET parliament_number = v.parliament_number "
                "FROM UNNEST(:ids, :parliament_numbers) AS v(id, parliament_number) "
                "WHERE speaker.id = v.id"
            ),
            {"ids": list(speaker_id_to_parliament_number.keys()), "parliament_numbers": list(speaker_id_to_parliament_number.values())},
        )

        return update_result.rowcount
