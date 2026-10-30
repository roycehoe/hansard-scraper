import argparse
from pathlib import Path

from sqlmodel import Session

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from database.init import engine
from database.speech import Speech
from exceptions import HansardWriteCheckError
from logs import logger
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"
_PREVIOUS_REVISION = "b8447a11fda2"
_REVISION = "82478ba59541"


def apply_speech_report_type(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    alembic_config = Config(str(_ALEMBIC_INI))
    with engine.connect() as connection:
        transaction = connection.begin()
        current_revision = MigrationContext.configure(connection).get_current_revision()
        if current_revision != _PREVIOUS_REVISION:
            raise HansardWriteCheckError(f"The database is at {current_revision}, not {_PREVIOUS_REVISION}")
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, _REVISION)
        command.check(alembic_config)
        if not is_commit:
            transaction.rollback()
            logger.info(f"Dry run: migration {_REVISION} and alembic check passed, then rolled back")
            return

        transaction.commit()
    logger.info(f"Committed: migration {_REVISION}, speech copied with its report type and swapped in")
    with Session(engine) as session:
        vacuum_analyze_written_tables(session, [Speech.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run migration 82478ba59541 and alembic check in one transaction: rolled back unless --commit")
    parser.add_argument("--commit", action="store_true", help="commit the copied speech table; without it the transaction rolls back")
    arguments = parser.parse_args()
    apply_speech_report_type(arguments.commit)
