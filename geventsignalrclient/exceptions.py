from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from requests import Response


class HubError(OSError):
    def __init__(self, *args: Any, response: Response, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.response = response

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: {self.response.status_code} - {self.response.text}"


class UnauthorizedHubError(HubError):
    pass


class HubConnectionError(ValueError):
    """Hub connection error."""

    pass
