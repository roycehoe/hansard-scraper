from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlmodel import Session


@dataclass(frozen=True)
class TableHash:
    row_count: int
    content_hash: str


class CRUDTableHash:
    def __init__(self, session: Session):
        self.session = session

    def get_table_names(self) -> list[str]:
        return sorted(inspect(self.session.connection()).get_table_names())

    def get_table_hash(self, table_name: str) -> TableHash:
        connection = self.session.connection()
        quote = connection.dialect.identifier_preparer.quote
        primary_key = inspect(connection).get_pk_constraint(table_name)["constrained_columns"]
        # NOTE: a table with no primary key is ordered by its row text, so equal content still hashes equal
        order_by = ", ".join(quote(column) for column in primary_key) or "row_text"
        statement = text(
            f"SELECT count(*), md5(coalesce(string_agg(row_hash, '' ORDER BY {order_by}), '')) "
            f"FROM (SELECT t::text AS row_text, md5(t::text) AS row_hash, t.* FROM {quote(table_name)} t) AS hashed"
        )
        row_count, content_hash = connection.execute(statement).one()
        return TableHash(row_count, content_hash)
