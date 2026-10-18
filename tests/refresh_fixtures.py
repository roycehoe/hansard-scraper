import copy
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Optional, Union

import httpx
from sqlmodel import Session

from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.hansard_website_response import HansardWebsiteResponse
from database.speaker import Speaker
from enums import ReportVersion
from exceptions import HansardGatewayError
from populate.speeches import (
    build_report_speeches,
    load_report_id_to_unattributed_range,
)
from schemas.constituency_names import ConstituencyNames
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from schemas.hansard_search_result import HansardSearchResult
from schemas.hansard_topic_response import HansardTopicResponse
from services.attendance import (
    build_constituency_lookups,
    build_sitting_attendances,
    build_speaker_lookups,
)
from services.hansard_website import get_topic_id
from services.report import build_report
from services.sitting import build_sitting
from utils.sitting_dates import parse_sitting_date

_FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "refresh"
_CONSTITUENCY_NAMES_FILE = Path(__file__).parent.parent / "data" / "constituency_names.json"
_SITTING_DETAIL_COLUMNS = ("sections", "annexures", "vernaculars", "a2b")


def load_fixture(name: str) -> dict:
    return json.loads((_FIXTURE_DIRECTORY / name).read_text(encoding="utf-8"))


def load_speaker_rows() -> list[dict]:
    return json.loads((_FIXTURE_DIRECTORY / "speakers.json").read_text(encoding="utf-8"))


def seed_stored(session: Session, speaker_names_to_drop: frozenset[str] = frozenset()) -> None:
    stored_sitting = load_fixture("stored_sitting.json")
    speakers = [Speaker(**speaker_row) for speaker_row in load_speaker_rows() if speaker_row["name"] not in speaker_names_to_drop]
    hansard_website_responses = [
        HansardWebsiteResponse.model_validate(website_response) for website_response in stored_sitting["website_responses"]
    ]
    reports = [build_report(hansard_website_response) for hansard_website_response in hansard_website_responses]
    hansard_sitting_date_response = HansardSittingDateResponse.model_validate(stored_sitting["sitting_date_response"])
    sitting = build_sitting(hansard_sitting_date_response)
    for column in _SITTING_DETAIL_COLUMNS:
        setattr(sitting, column, stored_sitting["sitting_details"][column])
    session.add_all([*speakers, *hansard_website_responses, *reports, hansard_sitting_date_response, sitting])
    session.flush()

    report_id_to_unattributed_range = load_report_id_to_unattributed_range()
    for report in reports:
        session.add_all(build_report_speeches(report, report_id_to_unattributed_range))
    constituency_lookups = build_constituency_lookups(ConstituencyNames.model_validate(json.loads(_CONSTITUENCY_NAMES_FILE.read_text())))
    session.add_all(build_sitting_attendances(sitting, build_speaker_lookups(speakers), constituency_lookups))
    session.commit()


def _build_search_result_body(website_response: dict) -> dict:
    return {
        "volumeNo": website_response["volume_number"],
        "parlNo": website_response["parliament_number"],
        "sittingNo": website_response["sitting_number"],
        "sittingDate": website_response["sitting_date"],
        "sno": website_response["speech_number"],
        "title": website_response["title"],
        "subtitle": website_response["subtitle"],
        "reportId": website_response["report_id"],
        "reportType": website_response["report_type"],
        "htmlFileName": website_response["html_file_name"],
        "reportVersion": website_response["report_version"],
        "columnStart": "",
        "columnEnd": "",
    }


def _build_topic_body(content: str, report_version: str) -> dict:
    if report_version == ReportVersion.SPRS3:
        return {"resultHTML": {"content": content}}
    return {"htmlContent": content}


def _build_sitting_body(sitting_date_response: dict, sitting_details: dict) -> dict:
    return {
        "metadata": {
            "parlimentNO": sitting_date_response["parlement_no"],
            "sessionNO": sitting_date_response["session_no"],
            "volumeNO": sitting_date_response["volume_no"],
            "sittingNO": sitting_date_response["sitting_no"],
            "dateToDisplay": sitting_date_response["date_to_display"],
        },
        "attendanceList": json.loads(sitting_date_response["attendance_list"]),
        "takesSectionVOList": json.loads(sitting_details["sections"]),
    }


def _get_date(sitting_date: str) -> date:
    return parse_sitting_date(sitting_date).date()


class FakeParliament:
    def __init__(self):
        stored_sitting = load_fixture("stored_sitting.json")
        new_sitting = load_fixture("new_sitting.json")
        stored_website_responses = stored_sitting["website_responses"]
        self.stored_search_results: list[dict] = [_build_search_result_body(website_response) for website_response in stored_website_responses]
        self.new_search_results: list[dict] = copy.deepcopy(new_sitting["search_results"])
        self.report_id_to_topic: dict[str, dict] = {
            website_response["report_id"]: _build_topic_body(website_response["content"], website_response["report_version"])
            for website_response in stored_website_responses
        }
        self.report_id_to_topic.update(copy.deepcopy(new_sitting["topics"]))
        self.stored_sitting_date = _get_date(stored_sitting["sitting_date_response"]["sitting_date"])
        self.stored_sitting: dict = _build_sitting_body(stored_sitting["sitting_date_response"], stored_sitting["sitting_details"])
        self.new_sitting_date = _get_date(self.new_search_results[0]["sittingDate"])
        self.new_sitting: dict = copy.deepcopy(new_sitting["sitting"])
        self.search_calls: list[tuple[date, date]] = []
        self.sitting_calls: list[str] = []
        self.topic_calls: list[str] = []
        self.on_search: Optional[Callable[[], None]] = None

    def get_all_hansard_search_results(self, from_date: date, to_date: date) -> list[HansardSearchResult]:
        self.search_calls.append((from_date, to_date))
        if self.on_search is not None:
            self.on_search()
        return [
            HansardSearchResult.model_validate(search_result)
            for search_result in [*self.stored_search_results, *self.new_search_results]
            if from_date <= _get_date(search_result["sittingDate"]) and _get_date(search_result["sittingDate"]) <= to_date
        ]

    def get_hansard_report_response(self, sitting_date: str) -> Union[HansardReportOldResponse, HansardReportNewResponse]:
        self.sitting_calls.append(sitting_date)
        if _get_date(sitting_date) == self.new_sitting_date:
            return HansardReportNewResponse.model_validate(self.new_sitting)
        if _get_date(sitting_date) == self.stored_sitting_date:
            return HansardReportNewResponse.model_validate(self.stored_sitting)
        raise HansardGatewayError("no sitting")

    async def get_hansard_topic_response_async(self, topic_id: str, client: httpx.AsyncClient) -> HansardTopicResponse:
        self.topic_calls.append(topic_id)
        for search_result in [*self.stored_search_results, *self.new_search_results]:
            report_id = search_result["reportId"]
            if get_topic_id(report_id, search_result["htmlFileName"], search_result["reportVersion"]) == topic_id:
                return HansardTopicResponse(**self.report_id_to_topic[report_id])
        raise HansardGatewayError(f"no topic {topic_id}")
