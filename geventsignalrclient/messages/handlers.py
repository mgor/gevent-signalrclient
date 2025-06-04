from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from geventsignalrclient.messages import (
        BaseMessage,
        CancelInvocationMessage,
        CompletionClientStreamMessage,
        CompletionMessage,
    )


class SubscribeCallback(TypedDict):
    next: Callable[[int], None]
    complete: Callable[[CompletionMessage | CompletionClientStreamMessage], None]
    error: Callable[[CancelInvocationMessage], None]


class StreamHandler:
    def __init__(self, event: str, invocation_id: str):
        self.event = event
        self.invocation_id = invocation_id
        self.logger = logging.getLogger('gevent-signalrcore')
        self.next_callback: Callable[[int], None] = lambda _: self.logger.warning("next stream handler fired, no callback configured")
        self.complete_callback: Callable[[CompletionMessage | CompletionClientStreamMessage], None] = lambda _: self.logger.warning("next complete handler fired, no callback configured")
        self.error_callback: Callable[[CancelInvocationMessage], None] = lambda _: self.logger.warning("next error handler fired, no callback configured")

    def subscribe(self, subscribe_callbacks: SubscribeCallback) -> None:
        error = "subscribe object must be a dict like"

        if (
            subscribe_callbacks is None
            or not isinstance(subscribe_callbacks, dict)
        ):
            raise TypeError(error)

        if (
            "next" not in subscribe_callbacks
            or "complete" not in subscribe_callbacks
            or "error" not in subscribe_callbacks
        ):
            raise KeyError(error)

        if (
            not callable(subscribe_callbacks["next"])
            or not callable(subscribe_callbacks["next"])
            or not callable(subscribe_callbacks["next"])
        ):
            raise ValueError("Suscribe callbacks must be functions")

        self.next_callback = subscribe_callbacks["next"]
        self.complete_callback = subscribe_callbacks["complete"]
        self.error_callback = subscribe_callbacks["error"]


class InvocationHandler:
    def __init__(self, invocation_id: str | None, complete_callback: Callable[[BaseMessage], None]):
        self.invocation_id = invocation_id
        self.complete_callback = complete_callback
