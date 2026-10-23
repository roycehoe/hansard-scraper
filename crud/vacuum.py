from sqlalchemy import text
from sqlmodel import Session


class CRUDVacuum:
    def __init__(self, session: Session):
        self.session = session

    def get_vacuum_count(self, table_name: str) -> int:
        statement = text("SELECT vacuum_count FROM pg_stat_user_tables WHERE relid = CAST(:table_name AS regclass)")
        return self.session.execute(statement, {"table_name": table_name}).scalar_one()

    # NOTE: the commit hands the autocommit connection back, so the session's next statement runs in a transaction
    def vacuum_analyze(self, table_name: str) -> None:
        quoted_table_name = self.session.get_bind().dialect.identifier_preparer.quote(table_name)
        statement = text(f"VACUUM (ANALYZE) {quoted_table_name}")
        self.session.connection(execution_options={"isolation_level": "AUTOCOMMIT"}).execute(statement)
        self.session.commit()
