import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Optional

import pytest
from pydantic import BaseModel, ValidationError

import utils.data_files as data_files_module
from enums import HandCheckFormOfAddress
from exceptions import HansardDataFileError
from schemas.attendance_cleanup import AttendanceCleanup
from schemas.bill_title_correction import BillTitleCorrections
from schemas.constituency_names import ConstituencyNames
from schemas.excluded_report_id import ExcludedReportIds
from schemas.hand_check_office_holder import (
    HandCheckOfficeHolder,
    HandCheckOfficeHolders,
)
from schemas.hand_kept_act_link import HandKeptActLinks
from schemas.hand_kept_bill import HandKeptBills
from schemas.hand_kept_member import HandKeptMember, HandKeptMembers
from schemas.head_of_state import HeadOfStateResult, HeadsOfState
from schemas.ministry_list import MinistrySeeAlsoEntries, OfficeTitleMinistryEntries
from schemas.party_affiliation import PartyAffiliationMemberships
from schemas.person_decision import PersonDecision, PersonDecisions
from schemas.person_name_spelling import PersonNameSpellingEntries
from schemas.speaker_override import SpeakerOverrides
from schemas.unattributed_speech import UnattributedSpeechRanges
from utils.data_files import (
    get_attendance_cleanup,
    get_bill_title_corrections,
    get_colonial_members,
    get_constituency_names,
    get_excluded_report_ids,
    get_hand_check_office_holders,
    get_hand_kept_act_links,
    get_hand_kept_bills,
    get_heads_of_state,
    get_ministry_names,
    get_ministry_see_also,
    get_office_title_ministries,
    get_party_affiliations,
    get_person_decisions,
    get_person_name_spellings,
    get_speaker_overrides,
    get_unattributed_speech_ranges,
    get_unscraped_members,
)

_DATA_DIRECTORY = Path(__file__).parent.parent / "data"
_DATA_FILE_SCHEMAS = (
    ("attendance_cleanup.json", AttendanceCleanup),
    ("bill_title_corrections.json", BillTitleCorrections),
    ("colonial_la_members.json", HandKeptMembers),
    ("constituency_names.json", ConstituencyNames),
    ("excluded_report_ids.json", ExcludedReportIds),
    ("hand_check_office_holders.json", HandCheckOfficeHolders),
    ("hand_kept_act_links.json", HandKeptActLinks),
    ("hand_kept_bills.json", HandKeptBills),
    ("heads_of_state.json", HeadsOfState),
    ("ministry_see_also.json", MinistrySeeAlsoEntries),
    ("office_title_ministries.json", OfficeTitleMinistryEntries),
    ("party_affiliations.json", PartyAffiliationMemberships),
    ("person_decisions.json", PersonDecisions),
    ("person_name_spellings.json", PersonNameSpellingEntries),
    ("speaker_overrides.json", SpeakerOverrides),
    ("unattributed_speech.json", UnattributedSpeechRanges),
    ("unscraped_members.json", HandKeptMembers),
)
_DATA_FILE_GETTERS = (
    get_attendance_cleanup,
    get_bill_title_corrections,
    get_colonial_members,
    get_constituency_names,
    get_excluded_report_ids,
    get_hand_check_office_holders,
    get_hand_kept_act_links,
    get_hand_kept_bills,
    get_heads_of_state,
    get_ministry_names,
    get_office_title_ministries,
    get_party_affiliations,
    get_person_decisions,
    get_person_name_spellings,
    get_speaker_overrides,
    get_unattributed_speech_ranges,
    get_unscraped_members,
)
_TYPO_KEY = "typo_key"
_SPEAKER_OVERRIDES_FILE_NAME = "speaker_overrides.json"
_EXCLUDED_REPORT_IDS_FILE_NAME = "excluded_report_ids.json"
_HAND_CHECK_OFFICE_HOLDERS_FILE_NAME = "hand_check_office_holders.json"
_MINISTRY_NAME_COUNT = 48


def _get_record_count(loaded: object) -> int:
    if isinstance(loaded, list):
        return len(loaded)
    assert isinstance(loaded, BaseModel)
    return sum(len(value) for _, value in loaded if isinstance(value, list))


def _get_object_paths(
    node: object, path: tuple[object, ...] = ()
) -> list[tuple[object, ...]]:
    if isinstance(node, dict):
        paths = [path]
        for key, child in node.items():
            paths += _get_object_paths(child, (*path, key))
        return paths
    if isinstance(node, list) and node:
        return _get_object_paths(node[0], (*path, 0))
    return []


def _get_person_decision(**fields: object) -> dict[str, object]:
    person_decision: dict[str, object] = {
        "person_name": "Terence Ho",
        "members": [{"name": "Terence Ho Wee San", "parliament_number": 13}],
        "decision": "name",
        "source": "A source.",
    }
    return person_decision | fields


def _get_hand_check_office_holder(**fields: object) -> dict[str, object]:
    hand_check_office_holder: dict[str, object] = {
        "office": "Speaker",
        "holder": "Yeoh Ghim Seng",
        "form_of_address": "MR",
        "first_day": "1970-01-01",
        "last_day": None,
        "source_url": "https://example.org/speaker",
    }
    return hand_check_office_holder | fields


@pytest.mark.parametrize("getter", _DATA_FILE_GETTERS)
def test_a_getter_returns_the_records_of_its_file(getter: Callable[[], object]) -> None:
    assert _get_record_count(getter()) > 0


def test_a_mistyped_key_raises_data_file_error_naming_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    speaker_overrides_file = tmp_path / _SPEAKER_OVERRIDES_FILE_NAME
    speaker_overrides_file.write_text(
        json.dumps(
            {"legislative_assembly_overrides": [], "party_overrides": [], _TYPO_KEY: 1}
        )
    )
    monkeypatch.setattr(
        data_files_module, "_SPEAKER_OVERRIDES_FILE", speaker_overrides_file
    )

    with pytest.raises(HansardDataFileError) as error:
        get_speaker_overrides()

    assert _SPEAKER_OVERRIDES_FILE_NAME in str(error.value)
    assert _TYPO_KEY in str(error.value)


def test_a_list_file_error_names_the_record_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    excluded_report_ids_file = tmp_path / _EXCLUDED_REPORT_IDS_FILE_NAME
    records = [
        {"report_id": "a", "kept_report_id": "b", "reason": "A reason."},
        {"report_id": "c", "kept_report_id": "d"},
    ]
    excluded_report_ids_file.write_text(json.dumps(records))
    monkeypatch.setattr(
        data_files_module, "EXCLUDED_REPORT_IDS_FILE", excluded_report_ids_file
    )

    with pytest.raises(HansardDataFileError) as error:
        get_excluded_report_ids()

    assert _EXCLUDED_REPORT_IDS_FILE_NAME in str(error.value)
    assert "1.reason" in str(error.value)


def test_a_missing_file_is_not_a_data_file_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        data_files_module,
        "_SPEAKER_OVERRIDES_FILE",
        tmp_path / _SPEAKER_OVERRIDES_FILE_NAME,
    )

    with pytest.raises(FileNotFoundError):
        get_speaker_overrides()


def test_a_malformed_json_file_raises_data_file_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    speaker_overrides_file = tmp_path / _SPEAKER_OVERRIDES_FILE_NAME
    speaker_overrides_file.write_text("{not json")
    monkeypatch.setattr(
        data_files_module, "_SPEAKER_OVERRIDES_FILE", speaker_overrides_file
    )

    with pytest.raises(HansardDataFileError, match="json_invalid"):
        get_speaker_overrides()


@pytest.mark.parametrize(("file_name", "schema"), _DATA_FILE_SCHEMAS)
def test_every_model_of_a_data_file_refuses_an_unknown_key(
    file_name: str, schema: type[BaseModel]
) -> None:
    file_bytes = (_DATA_DIRECTORY / file_name).read_bytes()

    for path in _get_object_paths(json.loads(file_bytes)):
        data = json.loads(file_bytes)
        node = data
        for step in path:
            node = node[step]
        node[_TYPO_KEY] = 1

        with pytest.raises(ValidationError, match=_TYPO_KEY):
            schema.model_validate(data)


def test_person_decision_refuses_an_unknown_key() -> None:
    with pytest.raises(ValidationError):
        PersonDecision.model_validate(_get_person_decision(sorce="A source."))


def test_person_decision_refuses_an_unlisted_decision_value() -> None:
    with pytest.raises(ValidationError):
        PersonDecision.model_validate(_get_person_decision(decision="split"))


def test_person_decision_refuses_a_name_decision_with_two_members() -> None:
    members = [
        {"name": "Terence Ho Wee San", "parliament_number": 13},
        {"name": "Terence Ho", "parliament_number": 15},
    ]

    with pytest.raises(ValidationError, match="exactly one member"):
        PersonDecision.model_validate(_get_person_decision(members=members))


@pytest.mark.parametrize("person_name", [None, ""])
def test_person_decision_refuses_a_name_decision_without_a_name(
    person_name: Optional[str],
) -> None:
    with pytest.raises(ValidationError, match="needs a person_name"):
        PersonDecision.model_validate(_get_person_decision(person_name=person_name))


@pytest.mark.parametrize("decision", ["distinct", "merge"])
def test_person_decision_refuses_a_link_decision_with_one_member(decision: str) -> None:
    with pytest.raises(ValidationError, match="at least two members"):
        PersonDecision.model_validate(
            _get_person_decision(decision=decision, person_name=None)
        )


def test_hand_kept_member_refuses_a_missing_comments_key() -> None:
    member = {
        "name": "David Marshall",
        "party": "Labour Front",
        "is_legislative_assembly": True,
        "parliament_number": 0,
    }

    with pytest.raises(ValidationError):
        HandKeptMember.model_validate(member)


def test_head_of_state_refuses_a_missing_comments_key() -> None:
    with pytest.raises(ValidationError):
        HeadOfStateResult.model_validate(
            {"name": "John Nicoll", "parliament_number": 0}
        )


def test_the_office_holder_getter_returns_the_records_of_its_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    office_holders_file = tmp_path / _HAND_CHECK_OFFICE_HOLDERS_FILE_NAME
    office_holders_file.write_text(json.dumps([_get_hand_check_office_holder()]))
    monkeypatch.setattr(
        data_files_module, "_HAND_CHECK_OFFICE_HOLDERS_FILE", office_holders_file
    )

    office_holders = get_hand_check_office_holders()

    assert [office_holder.holder for office_holder in office_holders] == [
        "Yeoh Ghim Seng"
    ]
    assert office_holders[0].form_of_address == HandCheckFormOfAddress.MR
    assert office_holders[0].first_day == date(1970, 1, 1)
    assert office_holders[0].last_day is None


def test_a_mistyped_office_holder_key_raises_data_file_error_naming_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    office_holders_file = tmp_path / _HAND_CHECK_OFFICE_HOLDERS_FILE_NAME
    office_holders_file.write_text(
        json.dumps([_get_hand_check_office_holder(**{_TYPO_KEY: 1})])
    )
    monkeypatch.setattr(
        data_files_module, "_HAND_CHECK_OFFICE_HOLDERS_FILE", office_holders_file
    )

    with pytest.raises(HansardDataFileError) as error:
        get_hand_check_office_holders()

    assert _HAND_CHECK_OFFICE_HOLDERS_FILE_NAME in str(error.value)
    assert _TYPO_KEY in str(error.value)


@pytest.mark.parametrize(
    "key",
    [
        "office",
        "holder",
        "form_of_address",
        "first_day",
        "last_day",
        "source_url",
    ],
)
def test_hand_check_office_holder_refuses_a_missing_key(key: str) -> None:
    office_holder = _get_hand_check_office_holder()
    del office_holder[key]

    with pytest.raises(ValidationError, match=key):
        HandCheckOfficeHolder.model_validate(office_holder)


@pytest.mark.parametrize("form_of_address", ["Mr", "Mdm", "mr", ""])
def test_hand_check_office_holder_refuses_a_form_of_address_outside_the_enum(
    form_of_address: str,
) -> None:
    office_holder = _get_hand_check_office_holder(form_of_address=form_of_address)

    with pytest.raises(ValidationError, match="form_of_address"):
        HandCheckOfficeHolder.model_validate(office_holder)


def test_the_ministry_names_are_distinct() -> None:
    ministry_names = get_ministry_names()

    assert len(ministry_names) == _MINISTRY_NAME_COUNT
    assert len(set(ministry_names)) == _MINISTRY_NAME_COUNT


def test_every_ministry_an_entry_or_a_see_also_names_is_in_the_ministry_names() -> None:
    ministry_names = set(get_ministry_names())

    for office_title_ministry in get_office_title_ministries():
        assert set(office_title_ministry.ministry_names) <= ministry_names
    for ministry_see_also in get_ministry_see_also():
        assert ministry_see_also.ministry_name in ministry_names
        assert ministry_see_also.see_also_ministry_name in ministry_names


def test_the_office_titles_are_distinct() -> None:
    office_printeds = [
        office_title_ministry.office_printed
        for office_title_ministry in get_office_title_ministries()
    ]

    assert len(set(office_printeds)) == len(office_printeds)


def test_the_ministry_see_also_file_is_empty() -> None:
    assert get_ministry_see_also() == []
