from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.check_attached_file_addresses as check_attached_file_addresses_script
from database.attached_file_pointer import AttachedFilePointer
from database.report import Report
from enums import (
    AttachedFileAddressFinding,
    AttachedFileAddressGroup,
    AttachedFilePointerShape,
    ReportType,
    ReportVersion,
)
from exceptions import HansardAttachedFileError
from schemas.attached_file_check import AttachedFileAddressResults
from schemas.sprs_file_response import SprsFileResponse
from scripts.check_attached_file_addresses import check_attached_file_addresses

_KNOWN_GOOD_VALUE = "20210202/annex-Annex 1.pdf"
_PLACEHOLDER_VALUE = "20170801/vernacular-null"
_ANNEX_VALUE = "20230301/annex-A.pdf"
_VERNACULAR_VALUE = "20230301/vernacular-V.pdf"
_PDF_VALUE = "PDFs/one.pdf"
_HTM_VALUE = "PDFs/two.htm"
_SECTION_FILE_VALUE = "100_20230301_S1_T1.pdf"
_NON_ASCII_VALUE = "20230301/annex-Café.pdf"
_TRAILING_SPACE_VALUE = "PDFs/trail.pdf "
_KNOWN_BAD_STEM = "known-bad-0000"
_SECTION_FILE_KNOWN_BAD_MARKER = "S9999_T9999"
_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_STORED_VALUES = (
    (AttachedFilePointerShape.DATED, _ANNEX_VALUE),
    (AttachedFilePointerShape.DATED, _VERNACULAR_VALUE),
    (AttachedFilePointerShape.PDFS, _PDF_VALUE),
    (AttachedFilePointerShape.PDFS, _HTM_VALUE),
    (AttachedFilePointerShape.SECTION_FILE, _SECTION_FILE_VALUE),
    (AttachedFilePointerShape.DATED, _NON_ASCII_VALUE),
    (AttachedFilePointerShape.PDFS, _TRAILING_SPACE_VALUE),
)


def _build_response(
    value: str,
    status_code: int = _HTTP_OK,
    content_type: Optional[str] = "application/pdf",
    content_disposition: Optional[str] = "attachment; filename=",
    is_body_empty: bool = False,
) -> SprsFileResponse:
    return SprsFileResponse(
        url=f"https://sprs.test/download?value={value}",
        status_code=status_code,
        content_type=content_type,
        content_disposition=(
            None if content_disposition is None else f"{content_disposition}{value}"
        ),
        is_body_empty=is_body_empty,
    )


def _is_known_bad(value: str) -> bool:
    return _KNOWN_BAD_STEM in value or _SECTION_FILE_KNOWN_BAD_MARKER in value


def _answer_like_sprs(value: str) -> SprsFileResponse:
    if _is_known_bad(value):
        return _build_response(
            value, content_type="text/html", content_disposition=None
        )
    return _build_response(value)


@pytest.fixture
def requested_values(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    requested: list[str] = []
    monkeypatch.setattr(
        check_attached_file_addresses_script,
        "build_read_only_engine",
        lambda database_url: scratch_engine,
    )
    _fake_gateway(monkeypatch, requested, _answer_like_sprs)
    return requested


def _fake_gateway(
    monkeypatch: pytest.MonkeyPatch,
    requested: list[str],
    answer: Callable[[str], SprsFileResponse],
) -> None:
    def get_fake_response(download_value: str) -> SprsFileResponse:
        requested.append(download_value)
        return answer(download_value)

    monkeypatch.setattr(
        check_attached_file_addresses_script,
        "get_sprs_file_response",
        get_fake_response,
    )


def _seed(session: Session) -> None:
    report = Report(
        volumeNo=14,
        parlNo=14,
        sittingNo=None,
        sittingDate=datetime(2023, 3, 1),
        sno=1,
        original_title="Sample",
        title="Sample",
        reportId="sprs-report-0001",
        reportType=ReportType.MOTION,
        content="",
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )
    session.add(report)
    session.flush()
    session.add_all(
        AttachedFilePointer(
            ordinal=ordinal,
            printed_text="Link",
            href=f"/search/search/download?value={value}",
            shape=shape,
            download_value=value,
            sprs_report_id=report.report_id,
        )
        for ordinal, (shape, value) in enumerate(_STORED_VALUES, 1)
    )
    session.commit()


def _read_results(
    output_path: Path,
) -> dict[str, tuple[AttachedFileAddressGroup, AttachedFileAddressFinding]]:
    return {
        result.value: (result.group, result.finding)
        for result in AttachedFileAddressResults.model_validate_json(
            output_path.read_text(encoding="utf-8")
        ).root
    }


def test_every_sampled_address_is_requested_once_and_the_results_are_written(
    scratch_session: Session, requested_values: list[str], tmp_path: Path
) -> None:
    _seed(scratch_session)

    check_attached_file_addresses(tmp_path / "addresses.json")

    results = _read_results(tmp_path / "addresses.json")
    assert set(results) == {
        *(value for _, value in _STORED_VALUES),
        _PLACEHOLDER_VALUE,
    }
    assert results[_ANNEX_VALUE] == (
        AttachedFileAddressGroup.DATED_ANNEX,
        AttachedFileAddressFinding.ANSWERED,
    )
    assert results[_PLACEHOLDER_VALUE][0] == AttachedFileAddressGroup.PLACEHOLDER
    assert len(requested_values) == len(set(requested_values))
    assert _KNOWN_GOOD_VALUE in requested_values


def test_the_gate_refuses_when_the_known_good_answers_404(
    scratch_session: Session,
    requested_values: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(scratch_session)
    _fake_gateway(
        monkeypatch,
        requested_values,
        lambda value: _build_response(value, status_code=_HTTP_NOT_FOUND),
    )

    with pytest.raises(HansardAttachedFileError, match="known-good"):
        check_attached_file_addresses(tmp_path / "addresses.json")

    assert requested_values == [_KNOWN_GOOD_VALUE]
    assert not (tmp_path / "addresses.json").exists()


def test_the_gate_refuses_when_the_known_good_answers_with_an_empty_body(
    scratch_session: Session,
    requested_values: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(scratch_session)
    _fake_gateway(
        monkeypatch,
        requested_values,
        lambda value: _build_response(value, is_body_empty=True),
    )

    with pytest.raises(HansardAttachedFileError, match="known-good"):
        check_attached_file_addresses(tmp_path / "addresses.json")


def test_the_gate_refuses_when_sprs_answers_everything_the_same_and_names_the_address(
    scratch_session: Session,
    requested_values: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(scratch_session)
    _fake_gateway(monkeypatch, requested_values, _build_response)

    with pytest.raises(HansardAttachedFileError) as error_info:
        check_attached_file_addresses(tmp_path / "addresses.json")

    assert f"20230301/annex-{_KNOWN_BAD_STEM}.pdf" in str(error_info.value)
    assert "status_code=200" in str(error_info.value)


def test_the_gate_refuses_when_answers_differ_only_by_an_echoed_name(
    scratch_session: Session,
    requested_values: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(scratch_session)
    _fake_gateway(
        monkeypatch,
        requested_values,
        lambda value: _build_response(
            value, content_disposition=f"attachment; filename=echo-{len(value)}-"
        ),
    )

    with pytest.raises(HansardAttachedFileError, match="made-up address"):
        check_attached_file_addresses(tmp_path / "addresses.json")


def test_an_htm_answer_matching_the_known_bad_is_unproven(
    scratch_session: Session,
    requested_values: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(scratch_session)

    def answer(value: str) -> SprsFileResponse:
        if value.endswith(".htm"):
            return _build_response(
                value, content_type="text/html", content_disposition=None
            )
        return _answer_like_sprs(value)

    _fake_gateway(monkeypatch, requested_values, answer)

    check_attached_file_addresses(tmp_path / "addresses.json")

    assert _read_results(tmp_path / "addresses.json")[_HTM_VALUE] == (
        AttachedFileAddressGroup.PDFS_HTM,
        AttachedFileAddressFinding.UNPROVEN,
    )


def test_an_htm_answer_with_an_echoed_name_is_unproven(
    scratch_session: Session,
    requested_values: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(scratch_session)

    def answer(value: str) -> SprsFileResponse:
        if value.endswith(".htm"):
            return _build_response(
                value,
                content_type="text/html",
                content_disposition="attachment; filename=",
            )
        return _answer_like_sprs(value)

    _fake_gateway(monkeypatch, requested_values, answer)

    check_attached_file_addresses(tmp_path / "addresses.json")

    assert (
        _read_results(tmp_path / "addresses.json")[_HTM_VALUE][1]
        == AttachedFileAddressFinding.UNPROVEN
    )


def test_a_200_with_an_empty_body_is_failed(
    scratch_session: Session,
    requested_values: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(scratch_session)

    def answer(value: str) -> SprsFileResponse:
        if value == _ANNEX_VALUE:
            return _build_response(value, is_body_empty=True)
        return _answer_like_sprs(value)

    _fake_gateway(monkeypatch, requested_values, answer)

    check_attached_file_addresses(tmp_path / "addresses.json")

    assert (
        _read_results(tmp_path / "addresses.json")[_ANNEX_VALUE][1]
        == AttachedFileAddressFinding.FAILED
    )


def test_an_htm_answering_404_is_failed(
    scratch_session: Session,
    requested_values: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(scratch_session)

    def answer(value: str) -> SprsFileResponse:
        if value == _HTM_VALUE:
            return _build_response(value, status_code=_HTTP_NOT_FOUND)
        return _answer_like_sprs(value)

    _fake_gateway(monkeypatch, requested_values, answer)

    check_attached_file_addresses(tmp_path / "addresses.json")

    assert (
        _read_results(tmp_path / "addresses.json")[_HTM_VALUE][1]
        == AttachedFileAddressFinding.FAILED
    )


def test_a_pdf_answering_like_the_known_bad_is_failed(
    scratch_session: Session,
    requested_values: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed(scratch_session)

    def answer(value: str) -> SprsFileResponse:
        if value == _PDF_VALUE:
            return _build_response(
                value, content_type="text/html", content_disposition=None
            )
        return _answer_like_sprs(value)

    _fake_gateway(monkeypatch, requested_values, answer)

    check_attached_file_addresses(tmp_path / "addresses.json")

    assert (
        _read_results(tmp_path / "addresses.json")[_PDF_VALUE][1]
        == AttachedFileAddressFinding.FAILED
    )


def test_an_existing_output_file_refuses_before_any_request(
    scratch_session: Session, requested_values: list[str], tmp_path: Path
) -> None:
    _seed(scratch_session)
    (tmp_path / "addresses.json").write_text("[]", encoding="utf-8")

    with pytest.raises(HansardAttachedFileError, match="already exists"):
        check_attached_file_addresses(tmp_path / "addresses.json")

    assert requested_values == []
