from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from exceptions import HansardDataFileError
from schemas.attendance_cleanup import AttendanceCleanup
from schemas.bill_title_correction import BillTitleCorrection, BillTitleCorrections
from schemas.constituency_names import ConstituencyNames
from schemas.excluded_report_id import ExcludedReportId, ExcludedReportIds
from schemas.hand_check_office_holder import (
    HandCheckOfficeHolder,
    HandCheckOfficeHolders,
)
from schemas.hand_kept_act_link import HandKeptActLink, HandKeptActLinks
from schemas.hand_kept_bill import HandKeptBill, HandKeptBills
from schemas.hand_kept_member import HandKeptMember, HandKeptMembers
from schemas.head_of_state import HeadOfStateResult, HeadsOfState
from schemas.ministry_list import (
    MinistryNames,
    MinistrySeeAlsoEntries,
    MinistrySeeAlsoEntry,
    OfficeTitleMinistryEntries,
    OfficeTitleMinistryEntry,
)
from schemas.office_check_minister import OfficeCheckMinister, OfficeCheckMinisters
from schemas.party_affiliation import (
    MembershipPartyAffiliations,
    PartyAffiliationMemberships,
)
from schemas.person_decision import PersonDecision, PersonDecisions
from schemas.person_name_spelling import (
    PersonNameSpellingEntries,
    PersonNameSpellingEntry,
)
from schemas.speaker_override import SpeakerOverrides
from schemas.unattributed_speech import (
    UnattributedSpeechRange,
    UnattributedSpeechRanges,
)

_DATA_DIRECTORY = Path(__file__).parent.parent / "data"
EXCLUDED_REPORT_IDS_FILE = _DATA_DIRECTORY / "excluded_report_ids.json"
_BILL_TITLE_CORRECTIONS_FILE = _DATA_DIRECTORY / "bill_title_corrections.json"
_CONSTITUENCY_NAMES_FILE = _DATA_DIRECTORY / "constituency_names.json"
_COLONIAL_MEMBERS_FILE = _DATA_DIRECTORY / "colonial_la_members.json"
_UNSCRAPED_MEMBERS_FILE = _DATA_DIRECTORY / "unscraped_members.json"
_SPEAKER_OVERRIDES_FILE = _DATA_DIRECTORY / "speaker_overrides.json"
_HAND_KEPT_ACT_LINKS_FILE = _DATA_DIRECTORY / "hand_kept_act_links.json"
_HAND_KEPT_BILLS_FILE = _DATA_DIRECTORY / "hand_kept_bills.json"
_HEADS_OF_STATE_FILE = _DATA_DIRECTORY / "heads_of_state.json"
_UNATTRIBUTED_SPEECH_FILE = _DATA_DIRECTORY / "unattributed_speech.json"
_PARTY_AFFILIATIONS_FILE = _DATA_DIRECTORY / "party_affiliations.json"
_ATTENDANCE_CLEANUP_FILE = _DATA_DIRECTORY / "attendance_cleanup.json"
_PERSON_DECISIONS_FILE = _DATA_DIRECTORY / "person_decisions.json"
_PERSON_NAME_SPELLINGS_FILE = _DATA_DIRECTORY / "person_name_spellings.json"
_HAND_CHECK_OFFICE_HOLDERS_FILE = _DATA_DIRECTORY / "hand_check_office_holders.json"
_MINISTRY_NAMES_FILE = _DATA_DIRECTORY / "ministry_names.json"
_OFFICE_TITLE_MINISTRIES_FILE = _DATA_DIRECTORY / "office_title_ministries.json"
_MINISTRY_SEE_ALSO_FILE = _DATA_DIRECTORY / "ministry_see_also.json"
_OFFICE_CHECK_MINISTERS_FILE = _DATA_DIRECTORY / "office_check_ministers.json"

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)


def _get_data_file(path: Path, schema: type[_SchemaT]) -> _SchemaT:
    try:
        return schema.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise HansardDataFileError(
            f"{path.name} does not match its schema: {error}"
        ) from error


def get_excluded_report_ids() -> list[ExcludedReportId]:
    return _get_data_file(EXCLUDED_REPORT_IDS_FILE, ExcludedReportIds).root


def get_constituency_names() -> ConstituencyNames:
    return _get_data_file(_CONSTITUENCY_NAMES_FILE, ConstituencyNames)


def get_colonial_members() -> list[HandKeptMember]:
    return _get_data_file(_COLONIAL_MEMBERS_FILE, HandKeptMembers).root


def get_unscraped_members() -> list[HandKeptMember]:
    return _get_data_file(_UNSCRAPED_MEMBERS_FILE, HandKeptMembers).root


def get_speaker_overrides() -> SpeakerOverrides:
    return _get_data_file(_SPEAKER_OVERRIDES_FILE, SpeakerOverrides)


def get_heads_of_state() -> list[HeadOfStateResult]:
    return _get_data_file(_HEADS_OF_STATE_FILE, HeadsOfState).root


def get_unattributed_speech_ranges() -> list[UnattributedSpeechRange]:
    return _get_data_file(_UNATTRIBUTED_SPEECH_FILE, UnattributedSpeechRanges).root


def get_party_affiliations() -> list[MembershipPartyAffiliations]:
    return _get_data_file(_PARTY_AFFILIATIONS_FILE, PartyAffiliationMemberships).root


def get_attendance_cleanup() -> AttendanceCleanup:
    return _get_data_file(_ATTENDANCE_CLEANUP_FILE, AttendanceCleanup)


def get_person_decisions() -> list[PersonDecision]:
    return _get_data_file(_PERSON_DECISIONS_FILE, PersonDecisions).root


def get_person_name_spellings() -> list[PersonNameSpellingEntry]:
    return _get_data_file(_PERSON_NAME_SPELLINGS_FILE, PersonNameSpellingEntries).root


def get_hand_check_office_holders() -> list[HandCheckOfficeHolder]:
    return _get_data_file(_HAND_CHECK_OFFICE_HOLDERS_FILE, HandCheckOfficeHolders).root


def get_bill_title_corrections() -> list[BillTitleCorrection]:
    return _get_data_file(_BILL_TITLE_CORRECTIONS_FILE, BillTitleCorrections).root


def get_hand_kept_bills() -> list[HandKeptBill]:
    return _get_data_file(_HAND_KEPT_BILLS_FILE, HandKeptBills).root


def get_hand_kept_act_links() -> list[HandKeptActLink]:
    return _get_data_file(_HAND_KEPT_ACT_LINKS_FILE, HandKeptActLinks).root


def get_ministry_names() -> list[str]:
    return _get_data_file(_MINISTRY_NAMES_FILE, MinistryNames).root


def get_office_title_ministries() -> list[OfficeTitleMinistryEntry]:
    return _get_data_file(
        _OFFICE_TITLE_MINISTRIES_FILE, OfficeTitleMinistryEntries
    ).root


def get_ministry_see_also() -> list[MinistrySeeAlsoEntry]:
    return _get_data_file(_MINISTRY_SEE_ALSO_FILE, MinistrySeeAlsoEntries).root


def get_office_check_ministers() -> list[OfficeCheckMinister]:
    return _get_data_file(_OFFICE_CHECK_MINISTERS_FILE, OfficeCheckMinisters).root
