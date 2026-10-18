from sqlmodel import Session, col, select

from database.party_affiliation import PartyAffiliation


class CRUDPartyAffiliation:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, party_affiliations: list[PartyAffiliation]) -> None:
        self.session.add_all(party_affiliations)
        self.session.flush()

    def get_by_speaker_ids(self, speaker_ids: list[int]) -> list[PartyAffiliation]:
        statement = select(PartyAffiliation).where(col(PartyAffiliation.speaker_id).in_(speaker_ids))
        return list(self.session.exec(statement).all())
