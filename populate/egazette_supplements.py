import hashlib
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from sqlmodel import Session

from crud.egazette_supplement import CRUDEgazetteSupplement, EgazetteSupplementRow
from database.egazette_supplement import EgazetteSupplement
from exceptions import HansardEgazetteSupplementError
from schemas.egazette_fetch import EgazetteFetchRecord, EgazetteFetchRecords
from schemas.egazette_supplement_plan import (
    EgazetteSupplementPlan,
    PlannedEgazetteSupplement,
    UnparsedEgazetteSupplement,
)
from services.egazette_supplement import (
    BILL_NUMBER_LINE,
    ParsedEgazetteSupplement,
    parse_egazette_supplement_text,
)
from utils.egazette_supplement_update import EgazetteSupplementUpdate

FETCH_RECORDS_FILE = "fetches.json"
_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_MAX_PAGES_READ = 4


@dataclass(frozen=True)
class EgazetteSupplementWrite:
    supplements_to_insert: list[PlannedEgazetteSupplement]
    supplement_updates: list[EgazetteSupplementUpdate]


def get_egazette_supplement_text(file_path: Path) -> str:
    text = ""
    for page in PdfReader(file_path).pages[:_MAX_PAGES_READ]:
        text += page.extract_text() + "\n"
        if BILL_NUMBER_LINE.search(text) is not None:
            break
    return text


def _get_checked_file_path(
    harvest_directory: Path, fetch_record: EgazetteFetchRecord
) -> Path:
    if fetch_record.file_path is None:
        raise HansardEgazetteSupplementError(
            f"{fetch_record.url} answered 200 with no file path"
        )
    file_path = harvest_directory / fetch_record.file_path
    file_sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
    if file_sha256 != fetch_record.sha256:
        raise HansardEgazetteSupplementError(
            f"{fetch_record.file_path} has SHA-256 {file_sha256}, the fetch record has {fetch_record.sha256}"
        )
    return file_path


def _build_planned_supplement(
    fetch_record: EgazetteFetchRecord, parsed_supplement: ParsedEgazetteSupplement
) -> PlannedEgazetteSupplement:
    if fetch_record.file_path is None:
        raise HansardEgazetteSupplementError(
            f"{fetch_record.url} answered 200 with no file path"
        )
    if fetch_record.size_bytes is None:
        raise HansardEgazetteSupplementError(
            f"{fetch_record.url} answered 200 with no size"
        )
    if fetch_record.sha256 is None:
        raise HansardEgazetteSupplementError(
            f"{fetch_record.url} answered 200 with no SHA-256"
        )
    return PlannedEgazetteSupplement(
        url=fetch_record.url,
        year=fetch_record.year,
        supplement_kind=fetch_record.supplement_kind,
        number=fetch_record.number,
        file_path=fetch_record.file_path,
        size_bytes=fetch_record.size_bytes,
        sha256=fetch_record.sha256,
        printed_title=parsed_supplement.printed_title,
        printed_bill_number=parsed_supplement.printed_bill_number,
        bill_number=parsed_supplement.bill_number,
        first_reading_date=parsed_supplement.first_reading_date,
        passing_date=parsed_supplement.passing_date,
        printed_act_number=parsed_supplement.printed_act_number,
        fetched_at=fetch_record.fetched_at,
    )


def get_egazette_supplement_plan(harvest_directory: Path) -> EgazetteSupplementPlan:
    fetch_records = EgazetteFetchRecords.model_validate_json(
        (harvest_directory / FETCH_RECORDS_FILE).read_text(encoding="utf8")
    ).root
    supplements: list[PlannedEgazetteSupplement] = []
    unparsed: list[UnparsedEgazetteSupplement] = []
    missing_count = 0
    for fetch_record in fetch_records:
        if fetch_record.status_code == _HTTP_FORBIDDEN:
            missing_count += 1
            continue
        if fetch_record.status_code != _HTTP_OK:
            raise HansardEgazetteSupplementError(
                f"{fetch_record.url} answered {fetch_record.status_code}"
            )
        file_path = _get_checked_file_path(harvest_directory, fetch_record)
        try:
            parsed_supplement = parse_egazette_supplement_text(
                get_egazette_supplement_text(file_path), fetch_record.supplement_kind
            )
        except HansardEgazetteSupplementError as error:
            unparsed.append(
                UnparsedEgazetteSupplement(url=fetch_record.url, message=str(error))
            )
            continue
        supplements.append(_build_planned_supplement(fetch_record, parsed_supplement))
    return EgazetteSupplementPlan(
        supplements=supplements, unparsed=unparsed, missing_count=missing_count
    )


def _build_update_from_row(
    egazette_supplement_row: EgazetteSupplementRow,
) -> EgazetteSupplementUpdate:
    return EgazetteSupplementUpdate(
        id=egazette_supplement_row.id,
        year=egazette_supplement_row.year,
        supplement_kind=egazette_supplement_row.supplement_kind,
        number=egazette_supplement_row.number,
        file_path=egazette_supplement_row.file_path,
        size_bytes=egazette_supplement_row.size_bytes,
        sha256=egazette_supplement_row.sha256,
        printed_title=egazette_supplement_row.printed_title,
        printed_bill_number=egazette_supplement_row.printed_bill_number,
        bill_number=egazette_supplement_row.bill_number,
        first_reading_date=egazette_supplement_row.first_reading_date,
        passing_date=egazette_supplement_row.passing_date,
        printed_act_number=egazette_supplement_row.printed_act_number,
        fetched_at=egazette_supplement_row.fetched_at,
    )


def _build_update_from_plan(
    row_id: int, planned_supplement: PlannedEgazetteSupplement
) -> EgazetteSupplementUpdate:
    return EgazetteSupplementUpdate(
        id=row_id,
        year=planned_supplement.year,
        supplement_kind=planned_supplement.supplement_kind,
        number=planned_supplement.number,
        file_path=planned_supplement.file_path,
        size_bytes=planned_supplement.size_bytes,
        sha256=planned_supplement.sha256,
        printed_title=planned_supplement.printed_title,
        printed_bill_number=planned_supplement.printed_bill_number,
        bill_number=planned_supplement.bill_number,
        first_reading_date=planned_supplement.first_reading_date,
        passing_date=planned_supplement.passing_date,
        printed_act_number=planned_supplement.printed_act_number,
        fetched_at=planned_supplement.fetched_at,
    )


def get_egazette_supplement_write(
    session: Session, plan: EgazetteSupplementPlan
) -> EgazetteSupplementWrite:
    url_to_egazette_supplement_row = {
        egazette_supplement_row.url: egazette_supplement_row
        for egazette_supplement_row in CRUDEgazetteSupplement(session).get_rows()
    }
    supplements_to_insert: list[PlannedEgazetteSupplement] = []
    supplement_updates: list[EgazetteSupplementUpdate] = []
    for planned_supplement in plan.supplements:
        egazette_supplement_row = url_to_egazette_supplement_row.get(
            planned_supplement.url
        )
        if egazette_supplement_row is None:
            supplements_to_insert.append(planned_supplement)
            continue
        planned_update = _build_update_from_plan(
            egazette_supplement_row.id, planned_supplement
        )
        if planned_update != _build_update_from_row(egazette_supplement_row):
            supplement_updates.append(planned_update)
    return EgazetteSupplementWrite(supplements_to_insert, supplement_updates)


def write_egazette_supplement_plan(
    session: Session, plan: EgazetteSupplementPlan
) -> None:
    egazette_supplement_write = get_egazette_supplement_write(session, plan)
    CRUDEgazetteSupplement(session).add_many(
        [
            EgazetteSupplement(
                url=planned_supplement.url,
                year=planned_supplement.year,
                supplement_kind=planned_supplement.supplement_kind,
                number=planned_supplement.number,
                file_path=planned_supplement.file_path,
                size_bytes=planned_supplement.size_bytes,
                sha256=planned_supplement.sha256,
                printed_title=planned_supplement.printed_title,
                printed_bill_number=planned_supplement.printed_bill_number,
                bill_number=planned_supplement.bill_number,
                first_reading_date=planned_supplement.first_reading_date,
                passing_date=planned_supplement.passing_date,
                printed_act_number=planned_supplement.printed_act_number,
                fetched_at=planned_supplement.fetched_at,
            )
            for planned_supplement in egazette_supplement_write.supplements_to_insert
        ]
    )
    CRUDEgazetteSupplement(session).update_many(
        egazette_supplement_write.supplement_updates
    )
