from __future__ import annotations


class HubError(OSError):
    pass


class UnauthorizedHubError(HubError):
    pass


class HubConnectionError(ValueError):
    """Hub connection error."""
    pass
