from sqlmodel import Session, col, delete, select

from database.person_name_spelling import PersonNameSpelling


class CRUDPersonNameSpelling:
    def __init__(self, session: Session):
        self.session = session

    def create_many(self, person_name_spellings: list[PersonNameSpelling]) -> None:
        self.session.add_all(person_name_spellings)
        self.session.flush()

    def get_all(self) -> list[PersonNameSpelling]:
        statement = select(PersonNameSpelling).order_by(
            col(PersonNameSpelling.person_id), col(PersonNameSpelling.ordinal)
        )
        return list(self.session.exec(statement).all())

    def delete_all(self) -> None:
        statement = delete(PersonNameSpelling)
        self.session.execute(statement)
        self.session.flush()
