import argparse
from collections import defaultdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.attached_file_pointer import CRUDAttachedFilePointer
from database.init import build_read_only_engine
from enums import AttachedFileAddressFinding, AttachedFileAddressGroup
from exceptions import HansardAttachedFileError
from logs import logger
from schemas.attached_file_check import (
    AttachedFileAddressResult,
    AttachedFileAddressResults,
    AttachedFileCheckFlag,
    AttachedFileCheckFlags,
    AttachedFileCollectedFlags,
    AttachedFileCollectedTieFlag,
)
from settings import settings

_KEPT_FINDINGS = (
    AttachedFileAddressFinding.UNPROVEN,
    AttachedFileAddressFinding.FAILED,
)


def _validate_can_write_collected_flags(output_path: Path) -> None:
    if output_path.exists():
        raise HansardAttachedFileError(f"{output_path} already exists")


def _get_pointer_to_flags(
    round_flags_paths: list[Path],
) -> dict[tuple[str, int], list[AttachedFileCheckFlag]]:
    pointer_to_flags: defaultdict[tuple[str, int], list[AttachedFileCheckFlag]] = (
        defaultdict(list)
    )
    for round_flags_path in round_flags_paths:
        for flag in AttachedFileCheckFlags.model_validate_json(
            round_flags_path.read_text(encoding="utf-8")
        ).root:
            pointer_to_flags[(flag.sprs_report_id, flag.pointer_ordinal)].append(flag)
    return pointer_to_flags


def _get_kept_addresses(
    address_results: list[AttachedFileAddressResult],
) -> list[AttachedFileAddressResult]:
    return sorted(
        (
            address_result
            for address_result in address_results
            if address_result.finding in _KEPT_FINDINGS
            and address_result.group != AttachedFileAddressGroup.PLACEHOLDER
        ),
        key=lambda address_result: (
            address_result.finding.value,
            address_result.group.value,
            address_result.value,
        ),
    )


def collect_attached_file_flags(
    round_flags_paths: list[Path],
    address_results_path: Optional[Path],
    output_path: Path,
) -> None:
    _validate_can_write_collected_flags(output_path)
    pointer_to_flags = _get_pointer_to_flags(round_flags_paths)
    if address_results_path is None:
        logger.info("The address check gave no results")
        address_results = []
    else:
        address_results = AttachedFileAddressResults.model_validate_json(
            address_results_path.read_text(encoding="utf-8")
        ).root

    with Session(build_read_only_engine(settings.database_url)) as session:
        pointer_to_current_tie = {
            (check_row.sprs_report_id, check_row.ordinal): (
                check_row.speech_ordinal,
                check_row.attached_file_id,
            )
            for check_row in CRUDAttachedFilePointer(
                session
            ).get_check_rows_by_speech_ordinal_not_null()
        }

    ties = []
    for pointer in sorted(pointer_to_flags):
        flags = pointer_to_flags[pointer]
        latest_flag = max(flags, key=lambda flag: flag.round_number)
        ties.append(
            AttachedFileCollectedTieFlag(
                flag=latest_flag,
                round_numbers=sorted({flag.round_number for flag in flags}),
                is_tie_unchanged=pointer_to_current_tie.get(pointer)
                == (latest_flag.speech_ordinal, latest_flag.attached_file_id),
            )
        )
    addresses = _get_kept_addresses(address_results)

    with output_path.open("x", encoding="utf-8") as output_file:
        output_file.write(
            AttachedFileCollectedFlags(ties=ties, addresses=addresses).model_dump_json(
                indent=2
            )
        )
    logger.info(
        f"{len(ties)} tie flags, of which {sum(1 for tie in ties if not tie.is_tie_unchanged)} no longer unchanged"
    )
    for finding in _KEPT_FINDINGS:
        logger.info(
            f"{finding.value} addresses: {sum(1 for address in addresses if address.finding == finding)}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collect the attached file check's flags and address results into one file, read only"
    )
    parser.add_argument(
        "--round-flags",
        type=Path,
        action="append",
        required=True,
        help="a round's flags file; repeat for each round",
    )
    parser.add_argument(
        "--address-results",
        type=Path,
        help="the address check's results; leave out when the check stopped at its gate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="the collected flags file; it may not exist yet",
    )
    arguments = parser.parse_args()
    collect_attached_file_flags(
        arguments.round_flags, arguments.address_results, arguments.output
    )
