import json
from pathlib import Path

from schemas.constituency_names import ConstituencyNames
from schemas.excluded_report_id import ExcludedReportId
from schemas.head_of_state import HeadOfStateResult
from schemas.speaker import SpeakerResult
from schemas.speaker_override import SpeakerOverrides
from schemas.unattributed_speech import UnattributedSpeechRange

_DATA_DIRECTORY = Path(__file__).parent.parent / "data"
EXCLUDED_REPORT_IDS_FILE = _DATA_DIRECTORY / "excluded_report_ids.json"
_CONSTITUENCY_NAMES_FILE = _DATA_DIRECTORY / "constituency_names.json"
_COLONIAL_MEMBERS_FILE = _DATA_DIRECTORY / "colonial_la_members.json"
_SPEAKER_OVERRIDES_FILE = _DATA_DIRECTORY / "speaker_overrides.json"
_HEADS_OF_STATE_FILE = _DATA_DIRECTORY / "heads_of_state.json"
_UNATTRIBUTED_SPEECH_FILE = _DATA_DIRECTORY / "unattributed_speech.json"


def get_excluded_report_ids() -> list[ExcludedReportId]:
    return [ExcludedReportId.model_validate(entry) for entry in json.loads(EXCLUDED_REPORT_IDS_FILE.read_text())]


def get_constituency_names() -> ConstituencyNames:
    return ConstituencyNames.model_validate(json.loads(_CONSTITUENCY_NAMES_FILE.read_text()))


def get_colonial_members() -> list[SpeakerResult]:
    return [SpeakerResult.model_validate(record) for record in json.loads(_COLONIAL_MEMBERS_FILE.read_text())]


def get_speaker_overrides() -> SpeakerOverrides:
    return SpeakerOverrides.model_validate(json.loads(_SPEAKER_OVERRIDES_FILE.read_text()))


def get_heads_of_state() -> list[HeadOfStateResult]:
    return [HeadOfStateResult.model_validate(record) for record in json.loads(_HEADS_OF_STATE_FILE.read_text())]


def get_unattributed_speech_ranges() -> list[UnattributedSpeechRange]:
    return [UnattributedSpeechRange.model_validate(entry) for entry in json.loads(_UNATTRIBUTED_SPEECH_FILE.read_text())]
