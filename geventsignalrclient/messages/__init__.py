from __future__ import annotations

from abc import ABCMeta
from enum import Enum
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from gevent.lock import Semaphore

if TYPE_CHECKING:
    from geventsignalrclient.connection import Connection


class MessageType(Enum):
    INVOCATION = 1
    STREAM_ITEM = 2
    COMPLETION = 3
    STREAM_INVOCATION = 4
    CANCEL_INVOCATION = 5
    PING = 6
    CLOSE = 7
    INVOCATION_BINDING_FAILURE = -1


class ErrorMessage(Protocol):
    error: str | None


class BaseMessage(metaclass=ABCMeta):
    def __init__(self, message_type: int | MessageType):
        self.type = MessageType(message_type) if isinstance(message_type, int) else message_type

    def __repr__(self) -> str:
        buffer: list[str] = [f"<{self.__class__.__name__}: "]

        sub_buffer: list[str] = []
        for key, value in self.__dict__.items():
            if key.startswith("_"):
                continue

            quote = '"' if isinstance(value, str) else ""

            sub_buffer.append(f"{key}={quote}{value}{quote}")

        buffer.append(", ".join(sub_buffer))
        buffer.append(">")

        return "".join(buffer)


class BaseHeadersMessage(BaseMessage):
    """All messages expct ping can carry aditional headers."""

    def __init__(self, message_type: int | MessageType, headers: dict[str, str] | None) -> None:
        super().__init__(message_type)
        self.headers = headers if headers is not None else {}


class CancelInvocationMessage(BaseHeadersMessage):
    """
    A `CancelInvocation` message is a JSON object with the following properties

    * `type` - A `Number` with the literal value `5`,
        indicating that this message is a `CancelInvocation`.
    * `invocationId` - A `String` encoding the `Invocation ID` for a message.

    Example
    ```json
    {
        "type": 5,
        "invocationId": "123"
    }
    """

    def __init__(self, *, invocation_id: str, headers: dict[str, str] | None) -> None:
        super().__init__(MessageType.CANCEL_INVOCATION, headers)
        self.invocation_id = invocation_id


class CloseMessage(BaseMessage):
    """
    A `Close` message is a JSON object with the following properties

    * `type` - A `Number` with the literal value `7`,
        indicating that this message is a `Close`.
    * `error` - An optional `String` encoding the error message.

    Example - A `Close` message without an error
    ```json
    {
        "type": 7
    }
    ```

    Example - A `Close` message with an error
    ```json
    {
        "type": 7,
        "error": "Connection closed because of an error!"
    }
    ```
    """

    def __init__(self, *, error: str | None) -> None:
        super().__init__(MessageType.CLOSE)
        self.error = error


class CompletionClientStreamMessage(BaseHeadersMessage):
    def __init__(self, *, invocation_id: str, headers: dict[str, str] | None) -> None:
        super().__init__(MessageType.COMPLETION, headers)
        self.invocation_id = invocation_id


class CompletionMessage(BaseHeadersMessage):
    """
    A `Completion` message is a JSON object with the following properties

    * `type` - A `Number` with the literal value `3`,
        indicating that this message is a `Completion`.
    * `invocationId` - A `String` encoding the `Invocation ID` for a message.
    * `result` - A `Token` encoding the result value
        (see "JSON Payload Encoding" for details).
        This field is **ignored** if `error` is present.
    * `error` - A `String` encoding the error message.

    It is a protocol error to include both a `result` and an `error` property
        in the `Completion` message. A conforming endpoint may immediately
        terminate the connection upon receiving such a message.

    Example - A `Completion` message with no result or error

    ```json
    {
        "type": 3,
        "invocationId": "123"
    }
    ```

    Example - A `Completion` message with a result

    ```json
    {
        "type": 3,
        "invocationId": "123",
        "result": 42
    }
    ```

    Example - A `Completion` message with an error

    ```json
    {
        "type": 3,
        "invocationId": "123",
        "error": "It didn't work!"
    }
    ```

    Example - The following `Completion` message is a protocol error
        because it has both of `result` and `error`

    ```json
    {
        "type": 3,
        "invocationId": "123",
        "result": 42,
        "error": "It didn't work!"
    }
    ```
    """

    def __init__(
        self, *, invocation_id: str, headers: dict[str, str] | None, result: int | None, error: str | None
    ) -> None:
        super().__init__(MessageType.COMPLETION, headers)
        self.invocation_id = invocation_id
        self.result = result
        self.error = error


class InvocationMessage(BaseHeadersMessage):
    """
    An `Invocation` message is a JSON object with the following properties:

    * `type` - A `Number` with the literal value 1, indicating that this message
        is an Invocation.
    * `invocationId` - An optional `String` encoding the `Invocation ID`
        for a message.
    * `target` - A `String` encoding the `Target` name, as expected by the Callee's
        Binder
    * `arguments` - An `Array` containing arguments to apply to the method
        referred to in Target. This is a sequence of JSON `Token`s,
            encoded as indicated below in the "JSON Payload Encoding" section

    Example:

    ```json
    {
        "type": 1,
        "invocationId": "123",
        "target": "Send",
        "arguments": [
            42,
            "Test Message"
        ]
    }
    ```
    Example (Non-Blocking):

    ```json
    {
        "type": 1,
        "target": "Send",
        "arguments": [
            42,
            "Test Message"
        ]
    }
    ```

    """

    def __init__(
        self, *, invocation_id: str | None, headers: dict[str, str] | None, target: str, arguments: list
    ) -> None:
        super().__init__(MessageType.INVOCATION, headers)
        self.invocation_id = invocation_id
        self.target = target
        self.arguments = arguments

    def __repr__(self):
        repr_str = "InvocationMessage: invocation_id {0}, target {1}, arguments {2}"
        return repr_str.format(self.invocation_id, self.target, self.arguments)


class InvocationClientStreamMessage(BaseHeadersMessage):
    def __init__(
        self,
        *,
        stream_ids: list[str],
        headers: dict[str, str] | None,
        target: str,
        arguments: tuple[int | str, int | str],
    ) -> None:
        super().__init__(MessageType.INVOCATION, headers)
        self.target = target
        self.arguments = arguments
        self.stream_ids = stream_ids

    def __repr__(self):
        repr_str = "InvocationMessage: stream_ids {0}, target {1}, arguments {2}"
        return repr_str.format(self.stream_ids, self.target, self.arguments)


class PingMessage(BaseMessage):
    """
    A `Ping` message is a JSON object with the following properties:

    * `type` - A `Number` with the literal value `6`,
        indicating that this message is a `Ping`.

    Example
    ```json
    {
        "type": 6
    }
    ```
    """

    def __init__(self) -> None:
        super().__init__(MessageType.PING)


class StreamInvocationMessage(BaseHeadersMessage):
    """
    A `StreamInvocation` message is a JSON object with the following properties:

    * `type` - A `Number` with the literal value 4, indicating that
        this message is a StreamInvocation.
    * `invocationId` - A `String` encoding the `Invocation ID` for a message.
    * `target` - A `String` encoding the `Target` name, as expected
        by the Callee's Binder.
    * `arguments` - An `Array` containing arguments to apply to
        the method referred to in Target. This is a sequence of JSON
        `Token`s, encoded as indicated below in the
        "JSON Payload Encoding" section.

    Example:

    ```json
    {
        "type": 4,
        "invocationId": "123",
        "target": "Send",
        "arguments": [
            42,
            "Test Message"
        ]
    }
    ```
    """

    def __init__(
        self, *, invocation_id: str, headers: dict[str, str] | None, target: str, arguments: tuple[int, str | int]
    ) -> None:
        super().__init__(MessageType.STREAM_INVOCATION, headers)
        self.invocation_id = invocation_id
        self.target = target
        self.arguments = arguments
        self.stream_ids: list[str] = []


class StreamItemMessage(BaseHeadersMessage):
    """
    A `StreamItem` message is a JSON object with the following properties:

    * `type` - A `Number` with the literal value 2, indicating
        that this message is a `StreamItem`.
    * `invocationId` - A `String` encoding the `Invocation ID` for a message.
    * `item` - A `Token` encoding the stream item
        (see "JSON Payload Encoding" for details).

    Example

    ```json
    {
        "type": 2,
        "invocationId": "123",
        "item": 42
    }
    ```
    """

    def __init__(self, *, invocation_id: str, headers: dict[str, str] | None, item: int) -> None:
        super().__init__(MessageType.STREAM_ITEM, headers)
        self.invocation_id = invocation_id
        self.item = item


class HandshakeRequestMessage(BaseMessage):
    def __init__(self, protocol: str, version: int) -> None:
        self.protocol = protocol
        self.version = version


class HandshakeResponseMessage(BaseMessage):
    def __init__(self, error: str | None) -> None:
        self.error = error


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
        self._connection: Connection | None = None
        self._target: str | None = None
        self.invocation_id = str(uuid4())
        self.lock = Semaphore()

    @property
    def connection(self) -> Connection:
        if self._connection is None:
            raise ValueError(self.error_message)

        return self._connection

    @connection.setter
    def connection(self, value: Connection) -> None:
        self._connection = value

    @property
    def target(self) -> str:
        if self._target is None:
            raise ValueError(self.error_message)

        return self._target

    @target.setter
    def target(self, value: str) -> None:
        self._target = value

    def next(self, item: int) -> None:
        """Send next item to the server

        Args:
            item (any): Item that will be streamed
        """
        with self.lock:
            self.connection.transport.send(
                StreamItemMessage(
                    invocation_id=self.invocation_id,
                    headers=None,
                    item=item,
                ),
            )

    def start(self):
        """Starts streaming"""
        with self.lock:
            self.connection.transport.send(
                InvocationClientStreamMessage(
                    stream_ids=[self.invocation_id],
                    target=self.target,
                    headers=None,
                    arguments=tuple(),
                ),
            )

    def complete(self):
        """Finish streaming"""
        with self.lock:
            self.connection.transport.send(
                CompletionClientStreamMessage(
                    invocation_id=self.invocation_id,
                    headers=None,
                ),
            )
