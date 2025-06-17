from __future__ import annotations

from geventsignalrclient.exceptions import HubConnectionError
from geventsignalrclient.messages import (
    BaseMessage,
    CancelInvocationMessage,
    CompletionMessage,
    ErrorMessage,
    InvocationMessage,
    MessageType,
    StreamInvocationMessage,
    StreamItemMessage,
    Subject,
)
from geventsignalrclient.messages.handlers import InvocationHandler, StreamHandler
from geventsignalrclient.protocol import JsonHubProtocol
from geventsignalrclient.transport import IntervalReconnectionHandler, RawReconnectionHandler, ReconnectionType
from geventsignalrclient.transport.websocket import WebsocketTransport

import logging
import sys
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Self, TypeGuard

if TYPE_CHECKING:
    from geventsignalrclient.protocol import BaseHubProtocol
    from geventsignalrclient.transport import ReconnectionHandler, ReconnectionParam

    from logging import Logger


class InvocationResult:
    def __init__(self, invocation_id: str) -> None:
        self.invocation_id = invocation_id
        self.message: InvocationMessage | Subject | None = None


class ConnectionBuilder:
    """
    Hub connection class, manages handshake and messaging

    Args:
        hub_url: SignalR core url

    Raises:
        HubConnectionError: Raises an Exception if url is empty or None
    """

    def __init__(self) -> None:
        self.hub_url: str
        self.hub = None
        self.options: dict = {"access_token_factory": None}
        self.token = None
        self.headers: dict[str, str] = dict()
        self.protocol: BaseHubProtocol | None = None
        self.reconnection_handler: ReconnectionHandler | None = None
        self.keep_alive_interval: int = 15
        self.verify_ssl: bool = True
        self.enable_trace: bool = False  # socket trace
        self.skip_negotiation: bool = False  # By default do not skip negotiation
        self.auth_function: Callable[[], str] | None = None
        self.logger: logging.Logger = logging.getLogger("gevent-signalrcore")

        logging.basicConfig(level=logging.CRITICAL)

    def with_url(self, hub_url: str, options: dict | None = None) -> Self:
        """Configure the hub url and options like negotiation and auth function
        import requests

        def login(self):
            response = requests.post(
                self.login_url,
                json={
                    "username": self.email,
                    "password": self.password
                    },verify=False)
            return response.json()["token"]

        self.connection = ConnectionBuilder().with_url(
            self.server_url,
            options={
                "verify_ssl": False,
                "access_token_factory": self.login,
                "headers": {
                    "mycustomheader": "mycustomheadervalue"
                }
            }).configure_logging(
                logging.ERROR,
            ).with_automatic_reconnect({
                "type": "raw",
                "keep_alive_interval": 10,
                "reconnect_interval": 5,
                "max_attempts": 5
            }).build()

        Args:
            hub_url (string): Hub URL
            options ([dict], optional): [description]. Defaults to None.

        Raises:
            ValueError: If url is invalid
            TypeError: If options are not a dict or auth function
                is not callable

        Returns:
            [ConnectionBuilder]: configured connection
        """
        if hub_url.strip() == "":
            raise ValueError("hub_url must be a valid url.")

        if options is not None and not isinstance(options, dict):
            raise TypeError("options must be a dictionary")

        self.options = options or {}

        if not callable(self.options.get("access_token_factory", hub_url.strip)):
            raise TypeError("access_token_factory must be a function without params")

        self.auth_function = self.options.get("access_token_factory", None)
        self.skip_negotiation = self.options.get("skip_negotiation", False)
        self.verify_ssl = self.options.get("verify_ssl", True)

        self.hub_url = hub_url
        self.hub = None

        self.headers.update(self.options.get("headers", {}))

        return self

    def with_logger(self, logger: logging.Logger) -> Self:
        self.logger = logger

        return self

    def configure_logging(
        self, logging_level: logging._Level, socket_trace: bool = False, handler: logging.Handler | None = None
    ) -> Self:
        """Configures signalr logging

        Args:
            logging_level ([type]): logging.INFO | logging.DEBUG ...
                from python logging class
            socket_trace (bool, optional): Enables socket package trace.
                Defaults to False.
            handler ([type], optional):  Custom logging handler.
                Defaults to None.

        Returns:
            [ConnectionBuilder]: Instance hub with logging configured
        """
        if handler is None:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging_level)
        else:
            logging.basicConfig(stream=sys.stdout, level=logging_level)

        self.enable_trace = socket_trace

        return self

    def with_hub_protocol(self, protocol: BaseHubProtocol) -> Self:
        """Changes transport protocol
            from signalrcore.protocol import MessagePackHubProtocol

            ConnectionBuilder().with_url(
                self.server_url, options={"verify_ssl":False},
            )
                ...
            ).with_hub_protocol(MessagePackHubProtocol())
                ...
            ).build()
        Args:
            protocol (JsonHubProtocol|MessagePackHubProtocol):
                protocol instance

        Returns:
            ConnectionBuilder: instance configured
        """
        self.protocol = protocol

        return self

    def build(self) -> Connection:
        """Configures the connection hub

        Raises:
            TypeError: Checks parameters an raises TypeError
                if one of them is wrong

        Returns:
            [ConnectionBuilder]: [self object for fluent interface purposes]
        """
        protocol = JsonHubProtocol() if self.protocol is None else self.protocol

        return Connection(
            headers=self.headers,
            auth_function=self.auth_function,
            url=self.hub_url,
            protocol=protocol,
            keep_alive_interval=self.keep_alive_interval,
            reconnection_handler=self.reconnection_handler,
            verify_ssl=self.verify_ssl,
            skip_negotiation=self.skip_negotiation,
            enable_trace=self.enable_trace,
            logger=self.logger,
        )

    def with_automatic_reconnect(self, param: ReconnectionParam) -> Self:
        """Configures automatic reconnection
            https://devblogs.microsoft.com/aspnet/asp-net-core-updates-in-net-core-3-0-preview-4/

            hub = ConnectionBuilder().with_url(
                self.server_url,
                options={"verify_ssl":False},
            ).configure_logging(
                logging.ERROR,
            ).with_automatic_reconnect({
                "type": "raw",
                "keep_alive_interval": 10,
                "reconnect_interval": 5,
                "max_attempts": 5
            }).build()

        Args:
            data (dict): [dict with autmatic reconnection parameters]

        Returns:
            [ConnectionBuilder]: [self object for fluent interface purposes]
        """
        reconnect_type = param.get("type", "raw")

        # Infinite reconnect attempts
        max_attempts = param.get("max_attempts", None)

        # 5 sec interval
        reconnect_interval: int = param.get("reconnect_interval", 5)

        self.keep_alive_interval = param.get("keep_alive_interval", 15)

        intervals: list[int] = param.get("intervals", [])  # Reconnection intervals

        reconnection_type = ReconnectionType[reconnect_type]

        if reconnection_type == ReconnectionType.raw:
            self.reconnection_handler = RawReconnectionHandler(reconnect_interval, max_attempts)
        elif reconnection_type == ReconnectionType.interval:
            self.reconnection_handler = IntervalReconnectionHandler(intervals)

        return self


class Connection:
    def __init__(
        self,
        headers: dict[str, str] | None,
        auth_function: Callable[[], str] | None,
        url: str,
        protocol: BaseHubProtocol | None,
        keep_alive_interval: int,
        reconnection_handler: ReconnectionHandler | None,
        verify_ssl: bool,
        skip_negotiation: bool,
        enable_trace: bool,
        logger: Logger,
    ) -> None:
        self.logger = logger
        self.url = url
        self.headers = {} if headers is None else headers
        self.auth_function = auth_function
        self.protocol: BaseHubProtocol = protocol or JsonHubProtocol()
        self.handlers: list[Callable | tuple[str, Callable]] = []
        self.stream_handlers: list[StreamHandler | InvocationHandler] = []
        self._on_error: Callable[[ErrorMessage], None] | None = None

        self.reconnection_handler = reconnection_handler

        self.transport = WebsocketTransport(
            connection=self,
            keep_alive_interval=keep_alive_interval,
            verify_ssl=verify_ssl,
            skip_negotiation=skip_negotiation,
            enable_trace=enable_trace,
        )

    def _refresh_token_maybe(self) -> None:
        if self.auth_function is not None:
            token = self.auth_function()
            if token is not None:
                self.headers.update({"Authorization": f"Bearer {token}"})

    def start(self) -> None:
        self._refresh_token_maybe()

        self.logger.debug("connection started")
        self.transport.start()

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

    def send(
        self,
        method,
        arguments: list | Subject,
        on_invocation: Callable[[BaseMessage], None] | None = None,
        invocation_id: str | None = None,
    ) -> InvocationResult:
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

        # for every send, make sure we have a fresh token
        if self.auth_function is not None:
            token = self.auth_function()
            if token is not None:
                self.headers.update({"Authorization": f"Bearer {token}"})

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
                self.logger.error("invocation binding failed for: %r", message)
                continue
            elif message.type == MessageType.PING:
                continue
            elif message.type == MessageType.INVOCATION and isinstance(
                message, InvocationMessage | StreamInvocationMessage
            ):
                invocation_filter: Callable[[Callable | tuple[str, Callable]], TypeGuard[tuple]] = (
                    lambda h: isinstance(h, tuple) and h[0] == message.target  # type: ignore[assignment]
                )
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
                completion_filter: Callable[
                    [StreamHandler | InvocationHandler], TypeGuard[StreamHandler | InvocationHandler]
                ] = lambda h: h.invocation_id == message.invocation_id  # type: ignore[assignment]
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
                item_filter: Callable[[InvocationHandler | StreamHandler], TypeGuard[StreamHandler]] = (
                    lambda h: isinstance(h, StreamHandler) and h.invocation_id == message.invocation_id  # type: ignore[assignment]
                )
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
                cancel_filter: Callable[[InvocationHandler | StreamHandler], TypeGuard[StreamHandler]] = (
                    lambda h: isinstance(h, StreamHandler) and h.invocation_id == message.invocation_id  # type: ignore[assignment]
                )
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
