import argparse
import hashlib
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from enums import EgazetteSupplementKind
from gateway.egazette import get_egazette_supplement_response
from logs import logger
from schemas.egazette_fetch import EgazetteFetchRecord, EgazetteFetchRecords

FETCH_RECORDS_FILE = "fetches.json"
_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_MAX_MISSING_RUN = 3
_REQUEST_GAP_SECONDS = 3.0
_SUPPLEMENT_KIND_TO_DIRECTORY = {
    EgazetteSupplementKind.BILLS: "bills",
    EgazetteSupplementKind.ACTS: "acts",
}


def _read_fetch_records(output_directory: Path) -> list[EgazetteFetchRecord]:
    try:
        return EgazetteFetchRecords.model_validate_json(
            (output_directory / FETCH_RECORDS_FILE).read_text(encoding="utf8")
        ).root
    except FileNotFoundError:
        return []


def _write_fetch_records(
    output_directory: Path, fetch_records: list[EgazetteFetchRecord]
) -> None:
    (output_directory / FETCH_RECORDS_FILE).write_text(
        EgazetteFetchRecords(fetch_records).model_dump_json(indent=1), encoding="utf8"
    )


def _fetch_supplement(
    output_directory: Path,
    year: int,
    supplement_kind: EgazetteSupplementKind,
    number: int,
) -> EgazetteFetchRecord:
    supplement_response = get_egazette_supplement_response(
        year, supplement_kind, number
    )
    fetched_at = datetime.now(timezone.utc)
    if supplement_response.status_code != _HTTP_OK:
        return EgazetteFetchRecord(
            url=supplement_response.url,
            year=year,
            supplement_kind=supplement_kind,
            number=number,
            status_code=supplement_response.status_code,
            fetched_at=fetched_at,
            file_path=None,
            size_bytes=None,
            sha256=None,
        )
    file_directory = (
        output_directory / str(year) / _SUPPLEMENT_KIND_TO_DIRECTORY[supplement_kind]
    )
    file_directory.mkdir(parents=True, exist_ok=True)
    file_path = file_directory / f"{number:02d}.pdf"
    file_path.write_bytes(supplement_response.content)
    return EgazetteFetchRecord(
        url=supplement_response.url,
        year=year,
        supplement_kind=supplement_kind,
        number=number,
        status_code=supplement_response.status_code,
        fetched_at=fetched_at,
        file_path=str(file_path.relative_to(output_directory)),
        size_bytes=len(supplement_response.content),
        sha256=hashlib.sha256(supplement_response.content).hexdigest(),
    )


def fetch_egazette_supplements(years: list[int], output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    fetch_records = _read_fetch_records(output_directory)
    fetched_keys = {
        (fetch_record.year, fetch_record.supplement_kind, fetch_record.number)
        for fetch_record in fetch_records
    }
    request_count = 0
    status_counts: Counter[int] = Counter()
    for year in years:
        for supplement_kind in EgazetteSupplementKind:
            missing_run = 0
            number = 1
            while missing_run < _MAX_MISSING_RUN:
                if (year, supplement_kind, number) not in fetched_keys:
                    fetch_record = _fetch_supplement(
                        output_directory, year, supplement_kind, number
                    )
                    request_count += 1
                    status_counts[fetch_record.status_code] += 1
                    fetch_records.append(fetch_record)
                    fetched_keys.add((year, supplement_kind, number))
                    _write_fetch_records(output_directory, fetch_records)
                    logger.info(
                        f"{fetch_record.url}: {fetch_record.status_code}, {fetch_record.size_bytes} bytes"
                    )
                    time.sleep(_REQUEST_GAP_SECONDS)
                stored_status = next(
                    fetch_record.status_code
                    for fetch_record in fetch_records
                    if (
                        fetch_record.year,
                        fetch_record.supplement_kind,
                        fetch_record.number,
                    )
                    == (year, supplement_kind, number)
                )
                missing_run = missing_run + 1 if stored_status == _HTTP_FORBIDDEN else 0
                number += 1
            logger.info(
                f"{year} {supplement_kind.value}: stopped at {number - 1} after {_MAX_MISSING_RUN} files answered 403"
            )
    logger.info(
        f"Requests to assets.egazette.gov.sg this run: {request_count}; by status: {dict(sorted(status_counts.items()))}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch the eGazette Bills Supplement and Acts Supplement PDFs of the given years into a harvest directory, 3 seconds apart, stopping each series after three files answer 403"
    )
    parser.add_argument("--year", type=int, action="append", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    fetch_egazette_supplements(arguments.year, arguments.output_directory)
