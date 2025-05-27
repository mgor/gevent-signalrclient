from __future__ import annotations

from signalrcore.exceptions import HubConnectionError
from signalrcore.messages import (
    BaseMessage,
    CancelInvocationMessage,
    CompletionMessage,
    ErrorMessage,
    InvocationMessage,
    MessageType,
    StreamInvocationMessage,
    StreamItemMessage,
)
from signalrcore.messages.handlers import InvocationHandler, StreamHandler
from signalrcore.messages.subject import Subject
from signalrcore.transport.websocket import WebsocketTransport

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeGuard

if TYPE_CHECKING:
    from signalrcore.protocol import BaseHubProtocol
    from signalrcore.transport import ReconnectionHandler

    from logging import Logger


class InvocationResult:
    def __init__(self, invocation_id: str) -> None:
        self.invocation_id = invocation_id
        self.message: InvocationMessage | Subject | None = None


class Connection:
    def __init__(
        self,
        headers: dict[str, Any] | None,
        auth_function: Callable[[], str] | None,
        url: str,
        protocol: BaseHubProtocol,
        keep_alive_interval: int,
        reconnection_handler: ReconnectionHandler | None,
        verify_ssl: bool,
        skip_negotiation: bool,
        enable_trace: bool,
        logger: Logger,
    ) -> None:
        self.headers = {} if headers is None else headers
        self.auth_function = auth_function
        self.logger = logger
        self.handlers: list[Callable | tuple[str, Callable]] = []
        self.stream_handlers: list[StreamHandler | InvocationHandler] = []
        self._on_error: Callable[[ErrorMessage], None] | None = None
        self.transport = WebsocketTransport(
            url=url,
            protocol=protocol,
            headers=self.headers,
            keep_alive_interval=keep_alive_interval,
            reconnection_handler=reconnection_handler,
            verify_ssl=verify_ssl,
            skip_negotiation=skip_negotiation,
            enable_trace=enable_trace,
            on_message=self.on_message,
            logger=self.logger,
        )

    def start(self) -> bool:
        if self.auth_function is not None:
            token = self.auth_function()
            if token is not None:
                self.headers.update({"Authorization": f"Bearer {token}"})

        self.logger.debug("connection started")
        return self.transport.start()

    def stop(self) -> None:
        self.logger.debug("connection stop")
        return self.transport.stop()

    def on_close(self, callback: Callable[[], None]) -> None:
        """Configures on_close connection callback.
            It will be raised on connection closed event
        connection.on_close(lambda: print("connection closed"))
        Args:
            callback (function): function without params
        """
        self.transport.on_close_callback(callback)

    def on_open(self, callback: Callable[[], None] | None) -> None:
        """Configures on_open connection callback.
            It will be raised on connection open event
        connection.on_open(lambda: print(
            "connection opened "))
        Args:
            callback (function): funciton without params
        """
        self.transport.on_open_callback(callback)

    def on_error(self, callback: Callable[[ErrorMessage], None] | None) -> None:
        """Configures on_error connection callback. It will be raised
            if any hub method throws an exception.
        connection.on_error(lambda data:
            print(f"An exception was thrown closed{data.error}"))
        Args:
            callback (function): function with one parameter.
                A CompletionMessage object.
        """
        self._on_error = callback

    def on_reconnect(self, callback: Callable[[], None] | None) -> None:
        """Configures on_reconnect reconnection callback.
            It will be raised on reconnection event
        connection.on_reconnect(lambda: print(
            "connection lost, reconnection in progress "))
        Args:
            callback (function): function without params
        """
        self.transport.on_reconnect_callback(callback)

    def on(self, event: str, callback_function: Callable) -> None:
        """Register a callback on the specified event
        Args:
            event (string):  Event name
            callback_function (Function): callback function,
                arguments will be binded
        """
        self.logger.debug("Handler registered started: %s", event)
        self.handlers.append((event, callback_function))

    def send(self, method, arguments: list | Subject, on_invocation: Callable[[BaseMessage], None] | None = None, invocation_id: str | None = None) -> InvocationResult:
        """Sends a message

        Args:
            method (string): Method name
            arguments (list|Subject): Method parameters
            on_invocation (function, optional): On invocation send callback
                will be raised on send server function ends. Defaults to None.
            invocation_id (string, optional): Override invocation ID. Exceptions
                thrown by the hub will use this ID, making it easier to handle
                with the on_error call.

        Raises:
            HubConnectionError: If hub is not ready to send
            TypeError: If arguments are invalid list or Subject
        """
        if invocation_id is None:
            invocation_id = str(uuid.uuid4())

        if not self.transport.is_running():
            raise HubConnectionError("Cannot connect to SignalR hub. Unable to transmit messages")

        if not isinstance(arguments, list | Subject):
            raise TypeError("Arguments of a message must be a list or subject")

        result = InvocationResult(invocation_id)

        if isinstance(arguments, list):
            message = InvocationMessage(
                invocation_id=invocation_id,
                target=method,
                arguments=arguments,
                headers=self.headers,
            )

            if on_invocation:
                self.stream_handlers.append(
                    InvocationHandler(
                        message.invocation_id,
                        on_invocation,
                    )
                )

            self.transport.send(message)
            result.message = message
        elif isinstance(arguments, Subject):
            arguments.connection = self
            arguments.target = method
            arguments.start()
            result.invocation_id = arguments.invocation_id
            result.message = arguments

        return result


    def on_message(self, messages: list[BaseMessage]) -> None:
        for message in messages:
            if message.type == MessageType.INVOCATION_BINDING_FAILURE:
                self.logger.error('invocation binding failed for: %r', message)
                continue
            elif message.type == MessageType.PING:
                continue
            elif message.type == MessageType.INVOCATION and isinstance(message, InvocationMessage | StreamInvocationMessage):
                invocation_filter: Callable[[Callable | tuple[str, Callable]], TypeGuard[tuple]] = lambda h: isinstance(h, tuple) and h[0] == message.target  # type: ignore[assignment]
                fired_invocation_handlers: list[tuple[str, Callable]] = list(
                    filter(
                        invocation_filter,
                        self.handlers,
                    ),
                )

                if len(fired_invocation_handlers) == 0:
                    self.logger.debug(f"event '{message.target}' hasn't fired any handler")

                for _, handler in fired_invocation_handlers:
                    handler(message.arguments)
            elif message.type == MessageType.CLOSE:
                self.logger.info("Close message received from server")
                self.stop()
                return
            elif message.type == MessageType.COMPLETION and isinstance(message, CompletionMessage):
                if message.error is not None and len(message.error) > 0 and self._on_error is not None:
                    self._on_error(message)

                # Send callbacks
                completion_filter: Callable[[StreamHandler | InvocationHandler], TypeGuard[StreamHandler | InvocationHandler]] = lambda h: h.invocation_id == message.invocation_id  # type: ignore[assignment]
                fired_completion_handlers: list[StreamHandler | InvocationHandler] = list(
                    filter(
                        completion_filter,
                        self.stream_handlers,
                    ),
                )

                # Stream callbacks
                for completion_handler in fired_completion_handlers:
                    completion_handler.complete_callback(message)

                # unregister handler
                self.stream_handlers = list(
                    filter(
                        lambda h: h.invocation_id != message.invocation_id,
                        self.stream_handlers,
                    ),
                )
            elif message.type == MessageType.STREAM_ITEM and isinstance(message, StreamItemMessage):
                item_filter: Callable[[InvocationHandler | StreamHandler], TypeGuard[StreamHandler]] = lambda h: isinstance(h, StreamHandler) and h.invocation_id == message.invocation_id  # type: ignore[assignment]
                fired_stream_handlers: list[StreamHandler] = list(
                    filter(
                        item_filter,
                        self.stream_handlers,
                    ),
                )

                if len(fired_stream_handlers) == 0:
                    self.logger.warning("id '%s' hasn't fire any stream handler", message.invocation_id)

                for stream_handler in fired_stream_handlers:
                    stream_handler.next_callback(message.item)
            elif message.type == MessageType.STREAM_INVOCATION:
                continue
            if message.type == MessageType.CANCEL_INVOCATION and isinstance(message, CancelInvocationMessage):
                cancel_filter: Callable[[InvocationHandler | StreamHandler], TypeGuard[StreamHandler]] = lambda h: isinstance(h, StreamHandler) and h.invocation_id == message.invocation_id  # type: ignore[assignment]
                fired_stream_handlers = list(
                    filter(
                        cancel_filter,
                        self.stream_handlers,
                    ),
                )

                if len(fired_stream_handlers) == 0:
                    self.logger.warning("id '%s' hasn't fire any stream handler", message.invocation_id)

                for stream_handler in fired_stream_handlers:
                    stream_handler.error_callback(message)

                # unregister handler
                self.stream_handlers = list(
                    filter(
                        lambda h: h.invocation_id != message.invocation_id,
                        self.stream_handlers,
                    ),
                )

    def stream(self, event: str, event_params: tuple[int, str | int]) -> StreamHandler:
        """Starts server streaming
            connection.stream(
            "Counter",
            (len(self.items), 500,)
            ).subscribe({
                "next": self.on_next,
                "complete": self.on_complete,
                "error": self.on_error
            })
        Args:
            event (string): Method Name
            event_params (list): Method parameters

        Returns:
            [StreamHandler]: stream handler
        """
        invocation_id = str(uuid.uuid4())
        stream_obj = StreamHandler(event, invocation_id)
        self.stream_handlers.append(stream_obj)
        self.transport.send(
            StreamInvocationMessage(
                invocation_id=invocation_id,
                target=event,
                arguments=event_params,
                headers=self.headers,
            ),
        )

        return stream_obj
