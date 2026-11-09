from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.collect_attached_file_flags as collect_attached_file_flags_script
from database.attached_file import AttachedFile
from database.attached_file_pointer import AttachedFilePointer
from database.report import Report
from database.sitting import Sitting
from enums import (
    AttachedFileAddressFinding,
    AttachedFileAddressGroup,
    AttachedFileCheckAnswer,
    AttachedFileKind,
    AttachedFilePointerShape,
    ParagraphTieRule,
    ReportType,
    ReportVersion,
)
from exceptions import HansardAttachedFileError
from schemas.attached_file_check import (
    AttachedFileAddressResult,
    AttachedFileAddressResults,
    AttachedFileCheckFlag,
    AttachedFileCheckFlags,
    AttachedFileCheckVerdict,
    AttachedFileCollectedFlags,
)
from schemas.sprs_file_response import SprsFileResponse
from scripts.collect_attached_file_flags import collect_attached_file_flags

_FIRST_REPORT_ID = "sprs-report-0001"
_SECOND_REPORT_ID = "sprs-report-0002"
_GONE_REPORT_ID = "sprs-report-0003"
_FIRST_ROUND = 1
_SECOND_ROUND = 2
_SPEECH_ORDINAL = 4
_OTHER_SPEECH_ORDINAL = 5
_HTTP_OK = 200


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _build_verdict(packet_id: str, note: str) -> AttachedFileCheckVerdict:
    return AttachedFileCheckVerdict(
        packet_id=packet_id,
        paragraph_answer=AttachedFileCheckAnswer.UNSURE,
        file_answer=None,
        note=note,
    )


def _build_flag(
    sprs_report_id: str,
    pointer_ordinal: int,
    round_number: int,
    speech_ordinal: int = _SPEECH_ORDINAL,
    attached_file_id: Optional[int] = None,
    note: str = "",
) -> AttachedFileCheckFlag:
    packet_id = f"packet-{round_number}-{sprs_report_id}-{pointer_ordinal}"
    return AttachedFileCheckFlag(
        packet_id=packet_id,
        round_number=round_number,
        sprs_report_id=sprs_report_id,
        pointer_ordinal=pointer_ordinal,
        speech_ordinal=speech_ordinal,
        attached_file_id=attached_file_id,
        link_words="Annex A",
        source_paragraph="See Annex A",
        row_transcript="See Annex A",
        file_title=None,
        paragraph_tie_rule=ParagraphTieRule.ONLY_OCCURRENCE,
        sonnet=_build_verdict(packet_id, note),
        opus=_build_verdict(packet_id, note),
    )


def _write_flags(path: Path, flags: list[AttachedFileCheckFlag]) -> Path:
    path.write_text(AttachedFileCheckFlags(flags).model_dump_json(), encoding="utf-8")
    return path


def _build_address_result(
    value: str,
    group: AttachedFileAddressGroup,
    finding: AttachedFileAddressFinding,
) -> AttachedFileAddressResult:
    answer = SprsFileResponse(
        url=f"https://sprs.test/download?value={value}",
        status_code=_HTTP_OK,
        content_type=None,
        content_disposition=None,
        is_body_empty=False,
    )
    return AttachedFileAddressResult(
        value=value,
        group=group,
        finding=finding,
        answer=answer,
        known_bad_answer=answer,
    )


def _build_report(report_id: str) -> Report:
    return Report(
        volumeNo=14,
        parlNo=14,
        sittingNo=None,
        sittingDate=datetime(2023, 3, 1),
        sno=1,
        original_title="Sample",
        title="Sample",
        reportId=report_id,
        reportType=ReportType.MOTION,
        content="",
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def _seed(session: Session) -> int:
    sitting = Sitting(parlement_no=14, sitting_date="1-3-2023")
    session.add(sitting)
    session.flush()
    assert sitting.id is not None
    attached_file = AttachedFile(
        kind=AttachedFileKind.ANNEX,
        sprs_file_id=1,
        printed_title="Annex A",
        printed_file_path="path",
        file_name="name",
        download_value="20230301/annex-A.pdf",
        sitting_id=sitting.id,
    )
    session.add_all(
        [
            attached_file,
            _build_report(_FIRST_REPORT_ID),
            _build_report(_SECOND_REPORT_ID),
        ]
    )
    session.flush()
    assert attached_file.id is not None
    session.add_all(
        [
            AttachedFilePointer(
                ordinal=1,
                printed_text="Annex A",
                href="/search/search/download?value=20230301/annex-A.pdf",
                shape=AttachedFilePointerShape.DATED,
                speech_ordinal=_SPEECH_ORDINAL,
                paragraph_tie_rule=ParagraphTieRule.ONLY_OCCURRENCE,
                sprs_report_id=_FIRST_REPORT_ID,
                attached_file_id=attached_file.id,
            ),
            AttachedFilePointer(
                ordinal=1,
                printed_text="Annex A",
                href="/search/search/download?value=20230301/annex-A.pdf",
                shape=AttachedFilePointerShape.DATED,
                speech_ordinal=_OTHER_SPEECH_ORDINAL,
                paragraph_tie_rule=ParagraphTieRule.ONLY_OCCURRENCE,
                sprs_report_id=_SECOND_REPORT_ID,
            ),
        ]
    )
    session.commit()
    return attached_file.id


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(
        collect_attached_file_flags_script,
        "build_read_only_engine",
        lambda database_url: scratch_engine,
    )
    monkeypatch.setattr(collect_attached_file_flags_script, "logger", recorder)
    return recorder


def _read_collected(output_path: Path) -> AttachedFileCollectedFlags:
    return AttachedFileCollectedFlags.model_validate_json(
        output_path.read_text(encoding="utf-8")
    )


def test_a_pointer_flagged_in_two_rounds_gives_one_entry_with_the_later_verdicts(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed(scratch_session)
    first_round_path = _write_flags(
        tmp_path / "round-1.json",
        [_build_flag(_FIRST_REPORT_ID, 1, _FIRST_ROUND, note="first round")],
    )
    second_round_path = _write_flags(
        tmp_path / "round-2.json",
        [_build_flag(_FIRST_REPORT_ID, 1, _SECOND_ROUND, note="second round")],
    )

    collect_attached_file_flags(
        [second_round_path, first_round_path], None, tmp_path / "files.json"
    )

    [tie] = _read_collected(tmp_path / "files.json").ties
    assert tie.round_numbers == [_FIRST_ROUND, _SECOND_ROUND]
    assert tie.flag.round_number == _SECOND_ROUND
    assert tie.flag.sonnet.note == "second round"


def test_a_tie_still_stored_is_unchanged_and_a_tie_that_moved_or_went_is_not(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    attached_file_id = _seed(scratch_session)
    flags_path = _write_flags(
        tmp_path / "round-1.json",
        [
            _build_flag(
                _FIRST_REPORT_ID, 1, _FIRST_ROUND, attached_file_id=attached_file_id
            ),
            _build_flag(
                _SECOND_REPORT_ID,
                1,
                _FIRST_ROUND,
                speech_ordinal=_SPEECH_ORDINAL,
            ),
            _build_flag(_GONE_REPORT_ID, 1, _FIRST_ROUND),
        ],
    )

    collect_attached_file_flags([flags_path], None, tmp_path / "files.json")

    report_id_to_unchanged = {
        tie.flag.sprs_report_id: tie.is_tie_unchanged
        for tie in _read_collected(tmp_path / "files.json").ties
    }
    assert report_id_to_unchanged == {
        _FIRST_REPORT_ID: True,
        _SECOND_REPORT_ID: False,
        _GONE_REPORT_ID: False,
    }


def test_answered_and_placeholder_addresses_are_left_out_and_the_rest_sorted(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed(scratch_session)
    flags_path = _write_flags(tmp_path / "round-1.json", [])
    addresses_path = tmp_path / "addresses.json"
    addresses_path.write_text(
        AttachedFileAddressResults(
            [
                _build_address_result(
                    "PDFs/b.htm",
                    AttachedFileAddressGroup.PDFS_HTM,
                    AttachedFileAddressFinding.UNPROVEN,
                ),
                _build_address_result(
                    "20230301/annex-A.pdf",
                    AttachedFileAddressGroup.DATED_ANNEX,
                    AttachedFileAddressFinding.ANSWERED,
                ),
                _build_address_result(
                    "20170801/vernacular-null",
                    AttachedFileAddressGroup.PLACEHOLDER,
                    AttachedFileAddressFinding.FAILED,
                ),
                _build_address_result(
                    "PDFs/a.htm",
                    AttachedFileAddressGroup.PDFS_HTM,
                    AttachedFileAddressFinding.UNPROVEN,
                ),
                _build_address_result(
                    "20230302/annex-B.pdf",
                    AttachedFileAddressGroup.DATED_ANNEX,
                    AttachedFileAddressFinding.FAILED,
                ),
            ]
        ).model_dump_json(),
        encoding="utf-8",
    )

    collect_attached_file_flags([flags_path], addresses_path, tmp_path / "files.json")

    assert [
        address.value for address in _read_collected(tmp_path / "files.json").addresses
    ] == ["20230302/annex-B.pdf", "PDFs/a.htm", "PDFs/b.htm"]


def test_no_address_results_gives_no_addresses_and_still_writes_the_tie_flags(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed(scratch_session)
    flags_path = _write_flags(
        tmp_path / "round-1.json", [_build_flag(_FIRST_REPORT_ID, 1, _FIRST_ROUND)]
    )

    collect_attached_file_flags([flags_path], None, tmp_path / "files.json")

    collected = _read_collected(tmp_path / "files.json")
    assert collected.addresses == []
    assert len(collected.ties) == 1
    assert "The address check gave no results" in log_recorder.messages


def test_an_existing_output_is_refused(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    flags_path = _write_flags(tmp_path / "round-1.json", [])
    (tmp_path / "files.json").write_text("{}", encoding="utf-8")

    with pytest.raises(HansardAttachedFileError, match="already exists"):
        collect_attached_file_flags([flags_path], None, tmp_path / "files.json")
