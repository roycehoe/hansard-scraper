class HansardError(Exception):
    """Base exception for all Hansard scraper errors."""


class HansardGatewayError(HansardError):
    """Raised when an HTTP request to the Hansard API fails."""
