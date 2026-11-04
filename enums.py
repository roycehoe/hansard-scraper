from enum import StrEnum


class ReportType(StrEnum):
    ORAL_ANSWER = "oral-answer"
    WRITTEN_ANSWER = "written-answer"
    WRITTEN_ANSWER_NOT_AVAILABLE = "written-answer-na"
    CLARIFICATION = "clarification"
    MOTION = "motion"
    ADJOURNMENT_MATTER = "matter-adj"
    BILL = "bill"
    BILL_INTRODUCTION = "bill-intro"
    MINISTERIAL_STATEMENT = "ministerial-statement"
    WRITTEN_STATEMENT = "written-statement"
    BUDGET = "budget"
    SPEAKER = "speaker"
    DEPUTY_SPEAKER = "deputy-speaker"
    PERSONAL_EXPLANATION = "personal-explanation"
    POINT_OF_ORDER = "point-of-order"
    TRIBUTE = "tribute"
    PRESIDENT_ADDRESS = "president-address"
    PETITION = "petition"
    ADMIN_OATHS = "admin-oaths"
    OBITUARY_SPEECH = "obituary-speech"
    YANG_DI_MESSAGE = "yang-di-message"
    MISCELLANEOUS = "misc"
    ATBP = "atbp"  # catch-all category


class ReportVersion(StrEnum):
    SPRS2 = "sprs2"  # older system, sittings before 10 September 2012
    SPRS3 = "sprs3"  # newer system, sittings from 10 September 2012


class SpeechKind(StrEnum):
    SPEECH = "SPEECH"
    PROCEDURAL = "PROCEDURAL"
    CHAMBER_EVENT = "CHAMBER_EVENT"
    EDITORIAL_NOTE = "EDITORIAL_NOTE"
    DOCUMENT_TEXT = "DOCUMENT_TEXT"
    HEADING = "HEADING"
    UNCLASSIFIED = "UNCLASSIFIED"


class ColumnNote(StrEnum):
    LIKELY_MISPRINT = "LIKELY_MISPRINT"
    SPEAKER_NAMED_IN_COLUMN_BEFORE = "SPEAKER_NAMED_IN_COLUMN_BEFORE"
    PRINTED_WITH_L_FOR_1 = "PRINTED_WITH_L_FOR_1"


class ReportAskerSource(StrEnum):
    ASKED_LINE = "ASKED_LINE"
    TO_ASK_LINE = "TO_ASK_LINE"
    STOOD_IN_NAME_LINE = "STOOD_IN_NAME_LINE"
    NAME_IN_TEXT = "NAME_IN_TEXT"
    CHAIR_CALL = "CHAIR_CALL"


class ParticipantRole(StrEnum):
    ASKER = "ASKER"
    ABSENT_FILER = "ABSENT_FILER"
    READER = "READER"
    ASKER_FOLLOW_UP = "ASKER_FOLLOW_UP"
    SUPPLEMENTARY = "SUPPLEMENTARY"
    ANSWERER = "ANSWERER"
    CHAIR = "CHAIR"
    UNLABELLED = "UNLABELLED"


class ParticipantRoleSource(StrEnum):
    ASKER_RULES = "ASKER_RULES"
    CHAIR_LABEL = "CHAIR_LABEL"
    CHAIR_NAME_CALL = "CHAIR_NAME_CALL"
    OFFICE_LABEL = "OFFICE_LABEL"
    OFFICE_ON_THE_DAY = "OFFICE_ON_THE_DAY"
    POSITION = "POSITION"
    AFTER_ANSWER = "AFTER_ANSWER"
    NO_RULE = "NO_RULE"
    QUESTION_NUMBER_CALL = "QUESTION_NUMBER_CALL"


class OfficeClass(StrEnum):
    PRIME_MINISTER = "PRIME_MINISTER"
    DEPUTY_PRIME_MINISTER = "DEPUTY_PRIME_MINISTER"
    MINISTER = "MINISTER"
    SENIOR_MINISTER_OF_STATE = "SENIOR_MINISTER_OF_STATE"
    MINISTER_OF_STATE = "MINISTER_OF_STATE"
    SENIOR_PARLIAMENTARY_SECRETARY = "SENIOR_PARLIAMENTARY_SECRETARY"
    PARLIAMENTARY_SECRETARY = "PARLIAMENTARY_SECRETARY"
    OTHER = "OTHER"


class OfficeSource(StrEnum):
    LABEL_IN_REPORT = "LABEL_IN_REPORT"
    HEADER_IN_REPORT = "HEADER_IN_REPORT"
    ATTENDANCE_LIST = "ATTENDANCE_LIST"
    LABEL_SAME_DAY = "LABEL_SAME_DAY"
    PARLIAMENT_GUESS = "PARLIAMENT_GUESS"


class QuestionState(StrEnum):
    NOT_ASKED_ALOUD = "NOT_ASKED_ALOUD"
    CORRECTION = "CORRECTION"
    URGENT = "URGENT"
    NOT_A_QUESTION = "NOT_A_QUESTION"


class MissingColumnReason(StrEnum):
    NO_MARKERS = "NO_MARKERS"
    TEXT_NOT_FOUND = "TEXT_NOT_FOUND"
    BEFORE_FIRST_MARKER = "BEFORE_FIRST_MARKER"
    SKIPPED_COLUMN = "SKIPPED_COLUMN"
    PAST_LAST_MARKER = "PAST_LAST_MARKER"
    BROKEN_SEQUENCE = "BROKEN_SEQUENCE"


class AttendanceCleanupReason(StrEnum):
    NOT_A_NAME = "NOT_A_NAME"
    OFFICE_FRAGMENT = "OFFICE_FRAGMENT"
    REPEATED_ATTENDEE = "REPEATED_ATTENDEE"
    OCR_ALIAS = "OCR_ALIAS"
    TRUNCATED_ENTRY = "TRUNCATED_ENTRY"
    SPEAKER_LINE = "SPEAKER_LINE"
    DECLINED_SEAT = "DECLINED_SEAT"
    PRESIDING_OFFICER = "PRESIDING_OFFICER"


class DatePrecision(StrEnum):
    DAY = "DAY"
    MONTH = "MONTH"


class RefreshRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    HALTED = "HALTED"
    FAILED = "FAILED"


class LegislativeAssemblyFlag(StrEnum):
    NO = "1"  # old site left these unflagged, all 1,253 rows
    YES = "2"  # old site flagged these, all 94 rows


class PersonDecisionKind(StrEnum):
    DISTINCT = "distinct"
    MERGE = "merge"
    NAME = "name"


class HandCheckFormOfAddress(StrEnum):
    MR = "MR"
    MDM = "MDM"


class HandCheckPlantKind(StrEnum):
    WRONG_MEMBER = "WRONG_MEMBER"
    CREDITED_NON_SPEECH_LINE = "CREDITED_NON_SPEECH_LINE"


class HandCheckMatchStatus(StrEnum):
    EXACT = "EXACT"
    INEXACT = "INEXACT"
    NOT_FOUND = "NOT_FOUND"


class HandCheckLiveCheckStatus(StrEnum):
    EQUAL = "EQUAL"
    DIFFERS = "DIFFERS"


class HandCheckAnswerStatus(StrEnum):
    TEXT = "TEXT"
    NO_CONTENT = "NO_CONTENT"
    ERROR = "ERROR"


class HandCheckSpeakerVerdict(StrEnum):
    RIGHT = "RIGHT"
    WRONG = "WRONG"
    RECORD_DOES_NOT_SAY = "RECORD_DOES_NOT_SAY"


class HandCheckDifferenceClass(StrEnum):
    LISTED_CHANGE = "LISTED_CHANGE"
    SUBSTANTIVE = "SUBSTANTIVE"
    COSMETIC = "COSMETIC"


class HandCheckErrorTier(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class HandCheckDifferenceKind(StrEnum):
    QUESTION_NUMBER = "QUESTION_NUMBER"
    LANGUAGE_NOTE = "LANGUAGE_NOTE"
    LABEL = "LABEL"
    CHAMBER_EVENT_CUT = "CHAMBER_EVENT_CUT"


class HandCheckFlagReason(StrEnum):
    SPEAKER_VERDICT = "SPEAKER_VERDICT"
    TEXT_DIFFERENCE = "TEXT_DIFFERENCE"
    MATCH_STATUS = "MATCH_STATUS"
    LIVE_TEXT_DIFFERS = "LIVE_TEXT_DIFFERS"
