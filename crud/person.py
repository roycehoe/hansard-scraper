from sqlmodel import Session, select

from database.person import Person


class CRUDPerson:
    def __init__(self, session: Session):
        self.session = session

    def create(self, person: Person) -> int:
        self.session.add(person)
        self.session.flush()
        return person.id

    def get_all(self) -> list[Person]:
        statement = select(Person)
        return list(self.session.exec(statement).all())

    def set_canonical_name(self, person: Person, canonical_name: str) -> None:
        person.canonical_name = canonical_name

        self.session.add(person)
        self.session.flush()
