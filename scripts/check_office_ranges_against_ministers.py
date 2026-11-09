import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.ministry import CRUDMinistry
from crud.office_printed_range import CRUDOfficePrintedRange, OfficePrintedRangeRow
from crud.office_title_ministry import CRUDOfficeTitleMinistry
from database.init import build_read_only_engine
from enums import OfficeCheckFlagKind
from exceptions import HansardOfficeCheckError
from logs import logger
from schemas.office_check_minister import OfficeCheckMinister
from settings import settings
from utils.data_files import get_office_check_ministers

_READ_ISOLATION_LEVEL = "REPEATABLE READ"


@dataclass(frozen=True)
class OfficeCheckRangeFlag:
    member_name: str
    ministry_name: str
    kind: OfficeCheckFlagKind
    office_printed: Optional[str]
    first_sitting_date: Optional[date]
    last_sitting_date: Optional[date]
    source_url: str


def get_office_check_flags(
    minister: OfficeCheckMinister,
    office_printed_range_rows: list[OfficePrintedRangeRow],
    office_printed_values_in_ministry: set[str],
) -> list[OfficeCheckRangeFlag]:
    flags: list[OfficeCheckRangeFlag] = []
    is_range_overlapping = False
    for office_printed_range_row in office_printed_range_rows:
        if (
            office_printed_range_row.office_printed
            not in office_printed_values_in_ministry
        ):
            continue
        first_sitting_date = office_printed_range_row.first_sitting_date.date()
        last_sitting_date = office_printed_range_row.last_sitting_date.date()
        if (
            first_sitting_date <= minister.end_date
            and last_sitting_date >= minister.start_date
        ):
            is_range_overlapping = True
        if (
            first_sitting_date < minister.start_date
            or last_sitting_date > minister.end_date
        ):
            flags.append(
                OfficeCheckRangeFlag(
                    minister.member_name,
                    minister.ministry_name,
                    OfficeCheckFlagKind.RANGE_OUTSIDE_DATES,
                    office_printed_range_row.office_printed,
                    first_sitting_date,
                    last_sitting_date,
                    minister.source_url,
                )
            )
    if not is_range_overlapping:
        flags.append(
            OfficeCheckRangeFlag(
                minister.member_name,
                minister.ministry_name,
                OfficeCheckFlagKind.NO_PRINT_INSIDE_DATES,
                None,
                None,
                None,
                minister.source_url,
            )
        )
    return flags


def _get_ministry_name_to_office_printed_values(
    session: Session,
) -> dict[str, set[str]]:
    ministry_id_to_name = {
        ministry.id: ministry.name for ministry in CRUDMinistry(session).get_all()
    }
    ministry_name_to_office_printed_values: defaultdict[str, set[str]] = defaultdict(
        set
    )
    for office_title_ministry_row in CRUDOfficeTitleMinistry(session).get_rows():
        ministry_name_to_office_printed_values[
            ministry_id_to_name[office_title_ministry_row.ministry_id]
        ].add(office_title_ministry_row.office_printed)
    return ministry_name_to_office_printed_values


def check_office_ranges_against_ministers(output_path: Path) -> None:
    ministers = get_office_check_ministers()
    if not ministers:
        logger.info("No ministers listed")
    flags: list[OfficeCheckRangeFlag] = []
    read_only_engine = build_read_only_engine(settings.database_url).execution_options(
        isolation_level=_READ_ISOLATION_LEVEL
    )
    with Session(read_only_engine) as session:
        ministry_names = {ministry.name for ministry in CRUDMinistry(session).get_all()}
        ministry_name_to_office_printed_values = (
            _get_ministry_name_to_office_printed_values(session)
        )
        for minister in ministers:
            if minister.ministry_name not in ministry_names:
                raise HansardOfficeCheckError(
                    f"Ministry {minister.ministry_name!r} of {minister.member_name} is not in the ministry table"
                )
            flags.extend(
                get_office_check_flags(
                    minister,
                    CRUDOfficePrintedRange(session).get_rows_by_speaker_ids(
                        minister.speaker_ids
                    ),
                    ministry_name_to_office_printed_values[minister.ministry_name],
                )
            )
    try:
        with output_path.open("x") as output_file:
            output_file.write(
                json.dumps([asdict(flag) for flag in flags], default=str, indent=1)
            )
    except FileExistsError as error:
        raise HansardOfficeCheckError(
            f"{output_path} exists; pass a path that does not"
        ) from error
    logger.info(
        f"{len(flags)} flags by kind: {dict(Counter(flag.kind for flag in flags))}; wrote {output_path}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check the printed office ranges against a table of ministers with known dates, read only"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="where to write the flags as JSON; an existing file is refused",
    )
    arguments = parser.parse_args()
    check_office_ranges_against_ministers(arguments.output)
