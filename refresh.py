import argparse
import sys
from datetime import datetime, timezone

from sqlmodel import Session

from database.init import engine
from enums import RefreshRunStatus
from populate.refresh_runs import populate_refresh_runs

_HALTED_EXIT_CODE = 2

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add new sittings, reports and speech rows from SPRS, and re-check the last 14 days")
    parser.add_argument("--allow-parliament", type=int, help="accept this one new Parliament number, for the supervised backfill")
    arguments = parser.parse_args()
    with Session(engine) as session:
        status = populate_refresh_runs(session, datetime.now(timezone.utc), arguments.allow_parliament)
    if status == RefreshRunStatus.HALTED:
        sys.exit(_HALTED_EXIT_CODE)
