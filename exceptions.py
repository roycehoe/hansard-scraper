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


class HansardRefreshRunError(HansardError):
    pass


class HansardTestGuardError(HansardError):
    pass
