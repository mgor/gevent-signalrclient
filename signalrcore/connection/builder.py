from __future__ import annotations

from signalrcore.protocol.json import JsonHubProtocol
from signalrcore.transport import IntervalReconnectionHandler, RawReconnectionHandler, ReconnectionType

import logging
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self

from . import Connection

if TYPE_CHECKING:
    from signalrcore.protocol import BaseHubProtocol
    from signalrcore.transport import ReconnectionHandler, ReconnectionParam


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
        self.options: dict[str, Any] = {
            "access_token_factory": None
        }
        self.token = None
        self.headers: dict[str, str] = dict()
        self.protocol: BaseHubProtocol | None = None
        self.reconnection_handler: ReconnectionHandler | None = None
        self.keep_alive_interval: int = 15
        self.verify_ssl: bool = True
        self.enable_trace: bool = False  # socket trace
        self.skip_negotiation: bool = False  # By default do not skip negotiation
        self.auth_function: Callable[[], str] | None = None
        self.logger: logging.Logger = logging.getLogger('gevent-signalrcore')

        logging.basicConfig(level=logging.CRITICAL)

    def with_url(self, hub_url: str, options: dict[str, Any] | None = None) -> Self:
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
            raise TypeError('options must be a dictionary')

        self.options = options or {}

        if not callable(self.options.get('access_token_factory', hub_url.strip)):
            raise TypeError("access_token_factory must be a function without params")

        self.auth_function = self.options.get('access_token_factory', None)
        self.skip_negotiation = self.options.get('skip_negotiation', False)
        self.verify_ssl = self.options.get('verify_ssl', True)

        self.hub_url = hub_url
        self.hub = None

        self.headers.update(self.options.get('headers', {}))

        return self

    def configure_logging(self, logging_level: logging._Level, socket_trace: bool = False, handler: logging.Handler | None = None) -> Self:
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
            handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )
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
