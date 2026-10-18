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
