import argparse
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from sqlmodel import Session

from crud.attached_file_pointer import (
    AttachedFilePointerAddressRow,
    CRUDAttachedFilePointer,
)
from database.init import build_read_only_engine
from enums import (
    AttachedFileAddressFinding,
    AttachedFileAddressGroup,
    AttachedFilePointerShape,
)
from exceptions import HansardAttachedFileError
from gateway.sprs_file import get_sprs_file_response
from logs import logger
from schemas.attached_file_check import (
    AttachedFileAddressResult,
    AttachedFileAddressResults,
)
from schemas.sprs_file_response import SprsFileResponse
from settings import settings

_SAMPLE_SEED = 20_261_211
_SAMPLE_PER_SHAPE = 50
_KNOWN_GOOD_VALUE = "20210202/annex-Annex 1.pdf"
_KNOWN_BAD_FILE_NAME_STEM = "known-bad-0000"
_PLACEHOLDER_VALUE = "20170801/vernacular-null"
_MINIMUM_ERROR_STATUS = 400
_DISPOSITION_TYPE_SEPARATOR = ";"
_FILE_NAME_WORD = "filename"
_PDF_EXTENSION = ".pdf"
_HTM_EXTENSION = ".htm"
_DATED_VERNACULAR_RE = re.compile(r"^\d{8}/vernacular-")
_SECTION_FILE_DATE_RE = re.compile(r"^\d+_(\d{8})_S\d+_T\d+\.pdf")
_KNOWN_BAD_SECTION_FILE_TEMPLATE = "999_{date}_S9999_T9999.pdf"
_PDFS_OTHER_NOTE = (
    "A PDFS_OTHER value that is not a .pdf is compared with the .pdf known-bad, "
    "so its ANSWERED proves less"
)


@dataclass(frozen=True)
class _ComparedAnswer:
    status_code: int
    content_type: Optional[str]
    disposition_type: Optional[str]
    has_file_name: bool
    is_body_empty: bool


@dataclass(frozen=True)
class _KnownBadValues:
    dated_annex: str
    pdf: str
    htm: str
    section_file: str


@dataclass(frozen=True)
class _KnownBadAnswers:
    dated_annex: SprsFileResponse
    pdf: SprsFileResponse
    htm: SprsFileResponse
    section_file: SprsFileResponse


def _get_compared_answer(sprs_file_response: SprsFileResponse) -> _ComparedAnswer:
    content_disposition = sprs_file_response.content_disposition
    return _ComparedAnswer(
        status_code=sprs_file_response.status_code,
        content_type=sprs_file_response.content_type,
        disposition_type=None
        if content_disposition is None
        else content_disposition.split(_DISPOSITION_TYPE_SEPARATOR, 1)[0]
        .strip()
        .lower(),
        has_file_name=content_disposition is not None
        and _FILE_NAME_WORD in content_disposition.lower(),
        is_body_empty=sprs_file_response.is_body_empty,
    )


def _get_address_group(
    shape: AttachedFilePointerShape, download_value: str
) -> AttachedFileAddressGroup:
    if shape == AttachedFilePointerShape.DATED:
        if _DATED_VERNACULAR_RE.match(download_value):
            return AttachedFileAddressGroup.DATED_VERNACULAR
        return AttachedFileAddressGroup.DATED_ANNEX
    if shape == AttachedFilePointerShape.PDFS:
        if PurePosixPath(download_value).suffix.lower() == _HTM_EXTENSION:
            return AttachedFileAddressGroup.PDFS_HTM
        return AttachedFileAddressGroup.PDFS_OTHER
    return AttachedFileAddressGroup.SECTION_FILE


def _get_first_value(values: list[str], description: str) -> str:
    try:
        return values[0]
    except IndexError as error:
        raise HansardAttachedFileError(
            f"No stored address is {description}, so no known-bad address can be built"
        ) from error


def _get_known_bad_values(
    value_to_group: dict[str, AttachedFileAddressGroup],
) -> _KnownBadValues:
    sorted_values = sorted(value_to_group)
    dated_annex_value = _get_first_value(
        [
            value
            for value in sorted_values
            if value_to_group[value] == AttachedFileAddressGroup.DATED_ANNEX
        ],
        "a dated annex",
    )
    pdf_value = _get_first_value(
        [
            value
            for value in sorted_values
            if value_to_group[value] == AttachedFileAddressGroup.PDFS_OTHER
            and PurePosixPath(value).suffix.lower() == _PDF_EXTENSION
        ],
        "a PDFs/ .pdf",
    )
    htm_value = _get_first_value(
        [
            value
            for value in sorted_values
            if value_to_group[value] == AttachedFileAddressGroup.PDFS_HTM
        ],
        "a PDFs/ .htm",
    )
    section_file_date = _get_first_value(
        [
            date_match.group(1)
            for date_match in (
                _SECTION_FILE_DATE_RE.match(value) for value in sorted_values
            )
            if date_match is not None
        ],
        "a section file",
    )
    return _KnownBadValues(
        dated_annex=f"{dated_annex_value.split('/', 1)[0]}/annex-{_KNOWN_BAD_FILE_NAME_STEM}{_PDF_EXTENSION}",
        pdf=f"{PurePosixPath(pdf_value).parent}/{_KNOWN_BAD_FILE_NAME_STEM}{_PDF_EXTENSION}",
        htm=f"{PurePosixPath(htm_value).parent}/{_KNOWN_BAD_FILE_NAME_STEM}{_HTM_EXTENSION}",
        section_file=_KNOWN_BAD_SECTION_FILE_TEMPLATE.format(date=section_file_date),
    )


def _validate_can_compare_with_known_good(
    known_good_answer: SprsFileResponse,
    known_bad_value: str,
    known_bad_answer: SprsFileResponse,
) -> None:
    compared_known_bad_answer = _get_compared_answer(known_bad_answer)
    if compared_known_bad_answer == _get_compared_answer(known_good_answer):
        raise HansardAttachedFileError(
            f"SPRS answers the made-up address {known_bad_value} as it answers the real one, {compared_known_bad_answer}"
        )


def _get_known_bad_answers(
    known_bad_values: _KnownBadValues, known_good_answer: SprsFileResponse
) -> _KnownBadAnswers:
    known_bad_answers = []
    for known_bad_value in (
        known_bad_values.dated_annex,
        known_bad_values.pdf,
        known_bad_values.htm,
        known_bad_values.section_file,
    ):
        known_bad_answer = get_sprs_file_response(known_bad_value)
        _validate_can_compare_with_known_good(
            known_good_answer, known_bad_value, known_bad_answer
        )
        known_bad_answers.append(known_bad_answer)
    return _KnownBadAnswers(*known_bad_answers)


def _get_sampled_values(
    value_to_group: dict[str, AttachedFileAddressGroup],
    value_to_extension: dict[str, str],
    generator: random.Random,
) -> dict[str, AttachedFileAddressGroup]:
    sample_key_to_values: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for value in sorted(value_to_group):
        sample_key_to_values[
            (value_to_group[value].value, value_to_extension[value])
        ].append(value)
    sampled_values: set[str] = set()
    for sample_key in sorted(sample_key_to_values):
        sample_values = sample_key_to_values[sample_key]
        sampled_values.update(
            generator.sample(sample_values, min(_SAMPLE_PER_SHAPE, len(sample_values)))
        )
    sampled_values.update(
        value for value in value_to_group if not value.isascii() or value.endswith(" ")
    )
    return {value: value_to_group[value] for value in sorted(sampled_values)}


def _get_known_bad_answer(
    group: AttachedFileAddressGroup, known_bad_answers: _KnownBadAnswers
) -> SprsFileResponse:
    if group == AttachedFileAddressGroup.PDFS_HTM:
        return known_bad_answers.htm
    if group == AttachedFileAddressGroup.PDFS_OTHER:
        return known_bad_answers.pdf
    if group == AttachedFileAddressGroup.SECTION_FILE:
        return known_bad_answers.section_file
    return known_bad_answers.dated_annex


def _get_finding(
    group: AttachedFileAddressGroup,
    answer: SprsFileResponse,
    known_bad_answer: SprsFileResponse,
) -> AttachedFileAddressFinding:
    if answer.status_code >= _MINIMUM_ERROR_STATUS or answer.is_body_empty:
        return AttachedFileAddressFinding.FAILED
    if _get_compared_answer(answer) == _get_compared_answer(known_bad_answer):
        if group == AttachedFileAddressGroup.PDFS_HTM:
            return AttachedFileAddressFinding.UNPROVEN
        return AttachedFileAddressFinding.FAILED
    return AttachedFileAddressFinding.ANSWERED


def _validate_can_write_address_results(output_path: Path) -> None:
    if output_path.exists():
        raise HansardAttachedFileError(f"{output_path} already exists")


def check_attached_file_addresses(output_path: Path) -> None:
    _validate_can_write_address_results(output_path)
    with Session(build_read_only_engine(settings.database_url)) as session:
        address_rows: list[AttachedFilePointerAddressRow] = CRUDAttachedFilePointer(
            session
        ).get_address_rows_by_download_value_not_null()
    value_to_group = {
        address_row.download_value: _get_address_group(
            address_row.shape, address_row.download_value
        )
        for address_row in address_rows
    }
    value_to_extension = {
        address_row.download_value: PurePosixPath(
            address_row.download_value
        ).suffix.lower()
        if address_row.shape == AttachedFilePointerShape.PDFS
        else ""
        for address_row in address_rows
    }

    known_good_answer = get_sprs_file_response(_KNOWN_GOOD_VALUE)
    if (
        known_good_answer.status_code >= _MINIMUM_ERROR_STATUS
        or known_good_answer.is_body_empty
    ):
        raise HansardAttachedFileError(
            f"SPRS gave no real answer for the known-good address {_KNOWN_GOOD_VALUE}: {_get_compared_answer(known_good_answer)}"
        )
    known_bad_answers = _get_known_bad_answers(
        _get_known_bad_values(value_to_group), known_good_answer
    )

    sampled_value_to_group = _get_sampled_values(
        value_to_group, value_to_extension, random.Random(_SAMPLE_SEED)
    )
    sampled_value_to_group[_PLACEHOLDER_VALUE] = AttachedFileAddressGroup.PLACEHOLDER
    results = []
    for value in sorted(sampled_value_to_group):
        group = sampled_value_to_group[value]
        answer = get_sprs_file_response(value)
        known_bad_answer = _get_known_bad_answer(group, known_bad_answers)
        results.append(
            AttachedFileAddressResult(
                value=value,
                group=group,
                finding=_get_finding(group, answer, known_bad_answer),
                answer=answer,
                known_bad_answer=known_bad_answer,
            )
        )

    with output_path.open("x", encoding="utf-8") as output_file:
        output_file.write(AttachedFileAddressResults(results).model_dump_json(indent=2))
    finding_to_count = Counter(result.finding for result in results)
    for finding in AttachedFileAddressFinding:
        logger.info(f"{finding.value}: {finding_to_count[finding]}")
    logger.info(_PDFS_OTHER_NOTE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check a sample of stored attached file addresses against SPRS, one request at a time"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="the results file; it may not exist yet",
    )
    arguments = parser.parse_args()
    check_attached_file_addresses(arguments.output)
