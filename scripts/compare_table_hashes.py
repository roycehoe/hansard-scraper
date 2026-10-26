import argparse
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlmodel import Session

from crud.table_hash import CRUDTableHash, TableHash
from logs import logger


def get_read_only_session(engine: Engine) -> Session:
    return Session(engine.execution_options(postgresql_readonly=True))


def get_table_hashes(engine: Engine) -> dict[str, TableHash]:
    with get_read_only_session(engine) as session:
        table_names = CRUDTableHash(session).get_table_names()
        return {table_name: CRUDTableHash(session).get_table_hash(table_name) for table_name in table_names}


def get_database_label(database_url: str) -> str:
    url = make_url(database_url)
    return f"{url.host}:{url.port}/{url.database}"


def _get_table_text(table_hash: Optional[TableHash]) -> str:
    return "missing" if table_hash is None else f"{table_hash.row_count} rows {table_hash.content_hash}"


def get_lines(first_label: str, first: dict[str, TableHash], second_label: str, second: dict[str, TableHash]) -> list[str]:
    lines = [f"Table hashes of {first_label} (first) and {second_label} (second)"]
    differing_tables = []
    for table_name in sorted(first.keys() | second.keys()):
        is_same = first.get(table_name) == second.get(table_name)
        if not is_same:
            differing_tables.append(table_name)
        lines.append(f"{table_name} | {_get_table_text(first.get(table_name))} | {_get_table_text(second.get(table_name))} | {'same' if is_same else 'DIFFERS'}")
    lines.append(f"Differing tables: {', '.join(differing_tables)}" if differing_tables else "No table differs")
    return lines


def compare_table_hashes(first_url: str, second_url: str, output_path: Optional[Path]) -> None:
    hashes = []
    for database_url in (first_url, second_url):
        # NOTE: the options are a second guard beside the read only session, and pin the settings that change how a value prints
        engine = create_engine(database_url, connect_args={"options": "-c default_transaction_read_only=on -c TimeZone=UTC -c DateStyle=ISO"})
        try:
            hashes.append(get_table_hashes(engine))
        finally:
            engine.dispose()
    lines = get_lines(get_database_label(first_url), hashes[0], get_database_label(second_url), hashes[1])
    for line in lines:
        logger.info(line)
    if output_path is not None:
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print a row count and a content hash for every table in two databases, read only, so a rehearsal copy can be compared with its source")
    parser.add_argument("first_url", help="database URL of the first database")
    parser.add_argument("second_url", help="database URL of the second database")
    parser.add_argument("--output", type=Path, help="write the lines to this path")
    arguments = parser.parse_args()
    compare_table_hashes(arguments.first_url, arguments.second_url, arguments.output)
