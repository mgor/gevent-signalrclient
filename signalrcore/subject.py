from __future__ import annotations

import uuid
from typing import Any, TYPE_CHECKING

import gevent
import gevent.lock

from .messages.invocation_message import InvocationClientStreamMessage
from .messages.stream_item_message import StreamItemMessage
from .messages.completion_message import CompletionClientStreamMessage

if TYPE_CHECKING:
    from .hub.base_hub_connection import BaseHubConnection


class Subject:
    """Client to server streaming
    https://docs.microsoft.com/en-gb/aspnet/core/signalr/streaming?view=aspnetcore-5.0#client-to-server-streaming
    items = list(range(0,10))
    subject = Subject()
    connection.send("UploadStream", subject)
    while(len(self.items) > 0):
        subject.next(str(self.items.pop()))
    subject.complete()
    """

    error_message = "subject must be passed as an argument to a send function. hub_connection.send([method], [subject])"

    def __init__(self) -> None:
        self._connection: BaseHubConnection | None = None
        self._target: str | None = None
        self.invocation_id = str(uuid.uuid4())
        self.lock = gevent.lock.RLock()

    @property
    def connection(self) -> BaseHubConnection:
        if self._connection is None:
            raise ValueError(self.error_message)

        return self._connection

    @connection.setter
    def connection(self, value: BaseHubConnection) -> None:
        self._connection = value

    @property
    def target(self) -> str:
        if self._target is None:
            raise ValueError(self.error_message)

        return self._target

    @target.setter
    def target(self, value: str) -> None:
        self._target = value

    def next(self, item: Any) -> None:
        """Send next item to the server

        Args:
            item (any): Item that will be streamed
        """
        with self.lock:
            self.connection.transport.send(
                StreamItemMessage(
                    self.invocation_id,
                    item,
                ),
            )

    def start(self):
        """Starts streaming
        """
        with self.lock:
            self.connection.transport.send(
                InvocationClientStreamMessage(
                    [self.invocation_id],
                    self.target,
                    [],
                ),
            )

    def complete(self):
        """Finish streaming
        """
        with self.lock:
            self.connection.transport.send(
                CompletionClientStreamMessage(
                    self.invocation_id,
                ),
            )
