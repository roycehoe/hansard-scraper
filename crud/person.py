from sqlmodel import Session

from database.person import Person


class CRUDPerson:
    def __init__(self, session: Session):
        self.session = session

    def create(self, person: Person) -> int:
        self.session.add(person)
        self.session.flush()
        return person.id
