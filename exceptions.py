class HansardError(Exception):
    pass


class HansardGatewayError(HansardError):
    pass


class HansardUnattributedSpeechError(HansardError):
    pass


class HansardWriteTargetError(HansardError):
    pass


class HansardWriteCheckError(HansardError):
    pass


class HansardPartyAffiliationError(HansardError):
    pass


class HansardTestGuardError(HansardError):
    pass
