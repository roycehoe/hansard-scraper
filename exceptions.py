class HansardError(Exception):
    pass


class HansardGatewayError(HansardError):
    pass


class HansardSearchRangeError(HansardError):
    pass


class HansardMemberListError(HansardError):
    pass


class HansardDataFileError(HansardError):
    pass


class HansardSittingReportError(HansardError):
    pass


class HansardUnattributedSpeechError(HansardError):
    pass


class HansardWriteTargetError(HansardError):
    pass


class HansardWriteCheckError(HansardError):
    pass


class HansardPartyAffiliationError(HansardError):
    pass


class HansardRefreshHaltError(HansardError):
    pass


class HansardRefreshFailureError(HansardError):
    pass


class HansardRefreshRunError(HansardError):
    pass


class HansardTestGuardError(HansardError):
    pass


class HansardHandCheckError(HansardError):
    pass


class HansardOfficeCheckError(HansardError):
    pass


class HansardActHistoryError(HansardError):
    pass


class HansardHandKeptEntryError(HansardError):
    pass


class HansardSsoListingError(HansardError):
    pass


class HansardActsSupplementError(HansardError):
    pass


class HansardBillsSupplementError(HansardError):
    pass


class HansardEgazetteSupplementError(HansardError):
    pass


class HansardRepealedActsListingError(HansardError):
    pass


class HansardReportLinkCheckError(HansardError):
    pass


class HansardBillKeyError(HansardError):
    pass


class HansardLawLinkCheckError(HansardError):
    pass


class HansardAttachedFileError(HansardError):
    pass
