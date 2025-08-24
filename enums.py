from enum import StrEnum


class ParliamentEntryType(StrEnum):
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
    ATBP = "atbp"  # “all that besides” / catch-all category
