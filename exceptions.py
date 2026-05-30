class HansardError(Exception):
    """Base exception for all Hansard scraper errors."""


class HansardGatewayError(HansardError):
    """Raised when an HTTP request to the Hansard API fails."""


class HansardParseError(HansardError):
    """Raised when Hansard response content cannot be parsed."""
