import json
import re
from functools import partial
from operator import attrgetter

import requests

from enums import LegislativeAssemblyFlag
from exceptions import HansardGatewayError
from gateway.http import CRAWL_HEADERS, send_with_retry
from schemas.parliament_member_list_response import ParliamentMemberListResponse
from schemas.speaker import SpeakerResult
from settings import settings

_SPEAKERS_TIMEOUT_SECONDS = 15
_FLIGHT_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_MEMBER_LIST_MARKER = '{"mps":'
_PARLIAMENT_TITLE_RE = re.compile(r"(\d+)(?:st|nd|rd|th) Parliament")
_NAME_WITH_COMMENT_RE = re.compile(r"^(.*?)\s*\((.+)\)\s*$")


def _get_parliament_member_list_response() -> ParliamentMemberListResponse:
    try:
        response = send_with_retry(
            partial(
                requests.get,
                url=settings.parliament_speakers_url,
                headers=CRAWL_HEADERS,
                timeout=_SPEAKERS_TIMEOUT_SECONDS,
            )
        )
        response.raise_for_status()
        flight_data = "".join(json.loads(chunk) for chunk in _FLIGHT_CHUNK_RE.findall(response.text))
        member_list, _ = json.JSONDecoder().raw_decode(flight_data, flight_data.index(_MEMBER_LIST_MARKER))
        parliament_member_list_response = ParliamentMemberListResponse.model_validate(member_list)
    except requests.exceptions.RequestException as error:
        raise HansardGatewayError("Member list request failed") from error
    except ValueError as error:
        raise HansardGatewayError("Member list page holds no readable member data") from error
    member_count = len(parliament_member_list_response.mps.data)
    if member_count != parliament_member_list_response.mps.meta.filter_count:
        raise HansardGatewayError(
            f"Member list holds {member_count} of {parliament_member_list_response.mps.meta.filter_count} members"
        )
    return parliament_member_list_response


def _get_parliament_number(parliament_title: str) -> int:
    match = _PARLIAMENT_TITLE_RE.fullmatch(parliament_title)
    if match is None:
        raise HansardGatewayError(f"Member list names an unreadable Parliament {parliament_title!r}")
    return int(match.group(1))


def _build_speaker_results(parliament_member_list_response: ParliamentMemberListResponse) -> list[SpeakerResult]:
    session_id_to_parliament_number = {
        session_id: _get_parliament_number(parliament.title)
        for parliament in parliament_member_list_response.options
        for session_id in parliament.parliament_sessions
    }
    speaker_results = []
    for member in parliament_member_list_response.mps.data:
        full_name = member.full_name.strip()
        match = _NAME_WITH_COMMENT_RE.match(full_name)
        name = full_name if match is None else match.group(1).strip()
        comments = None if match is None else match.group(2).strip()
        try:
            parliament_numbers = {
                session_id_to_parliament_number[session.parliament_sessions_id] for session in member.parliament_session
            }
        except KeyError as error:
            raise HansardGatewayError(f"Member list gives {full_name!r} a session of no listed Parliament") from error
        speaker_results.extend(
            SpeakerResult(
                name=name,
                party=member.party_affliation.strip(),
                is_legislative_assembly=member.legislative_assembly == LegislativeAssemblyFlag.YES,
                parliament_number=parliament_number,
                comments=comments,
            )
            for parliament_number in parliament_numbers
        )
    return sorted(speaker_results, key=attrgetter("parliament_number"))


def get_all_speakers() -> list[SpeakerResult]:
    return _build_speaker_results(_get_parliament_member_list_response())


def get_speakers_by_parliament_number(parliament_number: int) -> list[SpeakerResult]:
    speaker_results = [
        speaker_result for speaker_result in get_all_speakers() if speaker_result.parliament_number == parliament_number
    ]
    if not speaker_results:
        raise HansardGatewayError(f"No member list for parliament {parliament_number}")
    return speaker_results
