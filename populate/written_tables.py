from sqlmodel import Session

from crud.vacuum import CRUDVacuum
from exceptions import HansardWriteCheckError


# NOTE: call this after the script's own commit; VACUUM cannot run inside a transaction
def vacuum_analyze_written_tables(session: Session, table_names: list[str]) -> None:
    table_name_to_vacuum_count = {table_name: CRUDVacuum(session).get_vacuum_count(table_name) for table_name in table_names}
    # NOTE: nothing is pending; the commit ends the read transaction, which VACUUM cannot run inside
    session.commit()
    for table_name in table_names:
        CRUDVacuum(session).vacuum_analyze(table_name)
    for table_name, vacuum_count in table_name_to_vacuum_count.items():
        if CRUDVacuum(session).get_vacuum_count(table_name) == vacuum_count:
            raise HansardWriteCheckError(f"VACUUM (ANALYZE) did not run on {table_name}; Postgres skips a table the role cannot MAINTAIN")
