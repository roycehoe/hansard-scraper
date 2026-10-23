from pathlib import Path

import pytest
import requests

from enums import LegislativeAssemblyFlag
from exceptions import HansardGatewayError, HansardMemberListError
from gateway.http import CRAWL_PACER, CRAWL_USER_AGENT
from gateway.speakers_by_parliament import get_parliament_member_list_response
from schemas.parliament_member_list_response import (
    ParliamentMember,
    ParliamentMemberListResponse,
    ParliamentMembers,
    ParliamentMemberSession,
    ParliamentMembersMeta,
    ParliamentOption,
)
from schemas.speaker import SpeakerResult
from services.speaker import build_speaker_results
from settings import settings

_FIXTURE_FILE = Path(__file__).parent / "fixtures" / "parliament_member_list_page.html"
_FIFTEENTH_PARLIAMENT = 15
_FOURTEENTH_PARLIAMENT = 14
_FIRST_PARLIAMENT = 1
_FIFTEENTH_PARLIAMENT_MEMBER_COUNT = 108
_FOURTEENTH_PARLIAMENT_MEMBER_COUNT = 112
_FOURTEENTH_PARLIAMENT_COMMENT_COUNT = 9
_FIXTURE_MEMBER_COUNT_TEXT = 'filter_count\\":155'
_INFLATED_MEMBER_COUNT_TEXT = 'filter_count\\":156'
_LISTED_SESSION_ID = "session-15"
_UNLISTED_SESSION_ID = "session-99"
_READABLE_PARLIAMENT_TITLE = "15th Parliament"
_UNREADABLE_PARLIAMENT_TITLE = "Fifteenth Parliament"
_PAGE_WITHOUT_MEMBER_DATA = (
    "<html><body><h1>List of MPs By Parliament</h1>"
    "<script>(self.__next_f=self.__next_f||[]).push([0])</script>"
    "<script>self.__next_f.push([1,\"0:{\\\"P\\\":null}\\n\"])</script></body></html>"
)


class _FakePageResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        pass


def _skip_sleep(seconds: float) -> None:
    pass


@pytest.fixture
def no_op_pacer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CRAWL_PACER, "sleep", _skip_sleep)
    monkeypatch.setattr(CRAWL_PACER, "last_request_ended_at", None)


def _serve_page(monkeypatch: pytest.MonkeyPatch, page_html: str) -> None:
    def fake_get(url: str, headers: dict, **kwargs: object) -> _FakePageResponse:
        assert url == settings.parliament_speakers_url
        assert headers["User-Agent"] == CRAWL_USER_AGENT
        return _FakePageResponse(page_html)

    monkeypatch.setattr(requests, "get", fake_get)


def _get_speaker_result(speaker_results: list[SpeakerResult], name: str) -> SpeakerResult:
    return next(speaker_result for speaker_result in speaker_results if speaker_result.name == name)


def _get_all_speaker_results() -> list[SpeakerResult]:
    return build_speaker_results(get_parliament_member_list_response())


def _get_parliament_speaker_results(parliament_number: int) -> list[SpeakerResult]:
    return [
        speaker_result for speaker_result in _get_all_speaker_results() if speaker_result.parliament_number == parliament_number
    ]


def _get_member_list_response(parliament_title: str, member_session_id: str) -> ParliamentMemberListResponse:
    member = ParliamentMember(
        full_name="New Member",
        party_affliation="WP",
        legislative_assembly=LegislativeAssemblyFlag.NO,
        parliament_session=[ParliamentMemberSession(parliament_sessions_id=member_session_id)],
    )
    return ParliamentMemberListResponse(
        mps=ParliamentMembers(meta=ParliamentMembersMeta(filter_count=1), data=[member]),
        options=[ParliamentOption(title=parliament_title, parliament_sessions=[_LISTED_SESSION_ID])],
    )


def test_fifteenth_parliament_list(monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    _serve_page(monkeypatch, _FIXTURE_FILE.read_text())

    speaker_results = _get_parliament_speaker_results(_FIFTEENTH_PARLIAMENT)

    assert len(speaker_results) == _FIFTEENTH_PARLIAMENT_MEMBER_COUNT
    assert all(speaker_result.parliament_number == _FIFTEENTH_PARLIAMENT for speaker_result in speaker_results)
    assert _get_speaker_result(speaker_results, "Lawrence Wong") == SpeakerResult(
        name="Lawrence Wong",
        party="People’s Action Party",
        is_legislative_assembly=False,
        parliament_number=_FIFTEENTH_PARLIAMENT,
        comments=None,
    )


def test_fourteenth_parliament_list(monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    _serve_page(monkeypatch, _FIXTURE_FILE.read_text())

    speaker_results = _get_parliament_speaker_results(_FOURTEENTH_PARLIAMENT)

    assert len(speaker_results) == _FOURTEENTH_PARLIAMENT_MEMBER_COUNT
    assert len({speaker_result.name for speaker_result in speaker_results}) == _FOURTEENTH_PARLIAMENT_MEMBER_COUNT
    assert _get_speaker_result(speaker_results, "Pritam Singh") == SpeakerResult(
        name="Pritam Singh",
        party="Workers' Party",
        is_legislative_assembly=False,
        parliament_number=_FOURTEENTH_PARLIAMENT,
        comments=None,
    )


def test_bracket_after_the_name_becomes_the_comment(monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    _serve_page(monkeypatch, _FIXTURE_FILE.read_text())

    speaker_results = _get_parliament_speaker_results(_FOURTEENTH_PARLIAMENT)

    tharman = _get_speaker_result(speaker_results, "Tharman Shanmugaratnam")
    assert tharman.comments == "Resigned on 7 July 2023, 14th Parliament"
    assert _get_speaker_result(speaker_results, "Muhammad Faishal Ibrahim").comments == (
        "Resigned on 20 July 2026, 15th Parliament"
    )
    assert len([speaker_result for speaker_result in speaker_results if speaker_result.comments is not None]) == (
        _FOURTEENTH_PARLIAMENT_COMMENT_COUNT
    )
    assert all("(" not in speaker_result.name for speaker_result in speaker_results)


def test_whitespace_around_the_name_and_party_is_trimmed(monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    _serve_page(monkeypatch, _FIXTURE_FILE.read_text())

    speaker_results = _get_all_speaker_results()

    assert _get_speaker_result(speaker_results, "Derrick Goh").party == "People's Action Party"
    assert _get_speaker_result(speaker_results, "Audrey Wong Wai Yen").party == "Nominated Member of Parliament"


def test_assembly_flag_two_marks_an_assembly_member(monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    _serve_page(monkeypatch, _FIXTURE_FILE.read_text())

    speaker_results = _get_parliament_speaker_results(_FIRST_PARLIAMENT)

    assert _get_speaker_result(speaker_results, "Lee Kuan Yew").is_legislative_assembly is True


def test_all_speakers_come_in_parliament_order(monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    _serve_page(monkeypatch, _FIXTURE_FILE.read_text())

    parliament_numbers = [speaker_result.parliament_number for speaker_result in _get_all_speaker_results()]

    assert parliament_numbers == sorted(parliament_numbers)
    assert parliament_numbers.count(_FIFTEENTH_PARLIAMENT) == _FIFTEENTH_PARLIAMENT_MEMBER_COUNT


def test_page_without_member_data_raises(monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    _serve_page(monkeypatch, _PAGE_WITHOUT_MEMBER_DATA)

    with pytest.raises(HansardGatewayError):
        get_parliament_member_list_response()


def test_member_list_shorter_than_its_count_raises(monkeypatch: pytest.MonkeyPatch, no_op_pacer: None) -> None:
    _serve_page(monkeypatch, _FIXTURE_FILE.read_text().replace(_FIXTURE_MEMBER_COUNT_TEXT, _INFLATED_MEMBER_COUNT_TEXT))

    with pytest.raises(HansardGatewayError):
        get_parliament_member_list_response()


def test_unreadable_parliament_title_raises_member_list_error() -> None:
    with pytest.raises(HansardMemberListError):
        build_speaker_results(_get_member_list_response(_UNREADABLE_PARLIAMENT_TITLE, _LISTED_SESSION_ID))


def test_session_of_no_listed_parliament_raises_member_list_error() -> None:
    with pytest.raises(HansardMemberListError):
        build_speaker_results(_get_member_list_response(_READABLE_PARLIAMENT_TITLE, _UNLISTED_SESSION_ID))
