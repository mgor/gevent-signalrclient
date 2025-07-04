from __future__ import annotations

from geventsignalrclient.exceptions import HubError, UnauthorizedHubError
from geventsignalrclient.messages import BaseMessage, PingMessage

import logging
import sys
import urllib.parse as parse
from collections.abc import Callable
from contextlib import suppress
from logging import StreamHandler
from ssl import CERT_NONE
from time import time
from typing import TYPE_CHECKING, Any

import gevent
import requests
import websocket

from . import BaseTransport, ConnectionState

if TYPE_CHECKING:
    from geventsignalrclient.connection import Connection


class WebsocketTransport(BaseTransport):
    http_schemas: tuple[str, str] = ("http", "https")
    websocket_schemas: tuple[str, str] = ("ws", "wss")
    http_to_ws: dict[str, str] = {k: v for k, v in zip(http_schemas, websocket_schemas)}  # noqa: C416
    ws_to_http: dict[str, str] = {k: v for k, v in zip(websocket_schemas, http_schemas)}  # noqa: C416

    logging_levels: dict[int, str] = {v: k for k, v in logging.getLevelNamesMapping().items()}

    def __init__(
        self,
        connection: Connection,
        keep_alive_interval: int,
        verify_ssl: bool,
        skip_negotiation: bool,
        enable_trace: bool,
    ):
        super().__init__(
            connection=connection,
            keep_alive_interval=keep_alive_interval,
        )

        self._ws: websocket.WebSocketApp | None = None
        self._greenlet: gevent.Greenlet | None = None

        self.enable_trace = enable_trace
        self.skip_negotiation = skip_negotiation
        self.url = connection.url
        self.handshake_received: bool = False
        self._state: ConnectionState = ConnectionState.disconnected
        self.connection_alive: bool = False
        self.verify_ssl = verify_ssl

        if len(self.logger.handlers) > 0:
            try:
                stream_handler = next(
                    iter([handler for handler in self.logger.handlers if isinstance(handler, StreamHandler)])
                )
            except StopIteration:
                self.logger.exception("failed to find stream handler, use default")
                stream_handler = StreamHandler()

            logger = logging.getLogger("websocket")
            logger.setLevel("ERROR")
            websocket.enableTrace(self.enable_trace, stream_handler)

    @property
    def state(self) -> ConnectionState:
        return self._state

    @state.setter
    def state(self, value: ConnectionState) -> None:
        from_value = self._state

        self.logger.debug("changed connection state from %s -> %s", from_value.name, value.name)

        self._state = value

    @property
    def ws(self) -> websocket.WebSocketApp:
        if self._ws is None:
            raise ValueError("no websocket.WebSocketApp running")

        return self._ws

    @ws.setter
    def ws(self, value: websocket.WebSocketApp) -> None:
        self._ws = value

    def is_running(self) -> bool:
        return self.state != ConnectionState.disconnected

    def stop(self) -> None:
        if self.state == ConnectionState.connected:
            self.connection_checker.stop()
            if self._ws is not None:
                self._ws.close()
            self.state = ConnectionState.disconnected
            self.handshake_received = False

    def start(self) -> None:
        if not self.skip_negotiation:
            self.negotiate()

        if self.state == ConnectionState.connected:
            self.logger.warning("already connected unable to start")
            return

        self.state = ConnectionState.connecting
        self.logger.debug("start url: %s", self.url)

        self._ws = websocket.WebSocketApp(
            self.url,
            header=self.connection.headers,
            on_message=self.on_message,  # type: ignore[arg-type]
            on_error=self.on_socket_error,  # type: ignore[arg-type]
            on_close=self.on_close,  # type: ignore[arg-type]
            on_open=self.on_open,  # type: ignore[arg-type]
        )

        self._greenlet = gevent.spawn(
            self._ws.run_forever,
            sslopt={"cert_reqs": CERT_NONE} if not self.verify_ssl else {},
        )

    @classmethod
    def _replace_scheme(cls, url: str, ws: bool) -> str:
        """
        Replaces the scheme of a given URL from HTTP to WebSocket or vice versa.

        Args:
            url (str): The URL whose scheme is to be replaced.
            ws (bool): If True, replace HTTP with WebSocket schemes. If False, replace WebSocket with HTTP schemes.

        Returns:
            str: The URL with the replaced scheme.
        """
        scheme, netloc, path, query, fragment = parse.urlsplit(url)

        with suppress(KeyError):
            mapping = cls.http_to_ws if ws else cls.ws_to_http
            scheme = mapping[scheme]

        return parse.urlunsplit((scheme, netloc, path, query, fragment))

    @classmethod
    def _get_negotiate_url(cls, url: str) -> str:
        """
        Constructs the negotiation URL for the given SignalR endpoint URL.

        Args:
            url (str): The base SignalR endpoint URL.

        Returns:
            str: The negotiation URL.
        """
        scheme, netloc, path, query, fragment = parse.urlsplit(url)

        path = path.rstrip("/") + "/negotiate"
        with suppress(KeyError):
            scheme = cls.ws_to_http[scheme]

        return parse.urlunsplit((scheme, netloc, path, query, fragment))

    @classmethod
    def encode_connection_id(cls, url: str, id: str) -> str:
        url_parts = parse.urlsplit(url)
        query_string_parts = parse.parse_qs(url_parts.query)
        query_string_parts["id"] = [id]

        url_parts = url_parts._replace(query=parse.urlencode(query_string_parts, doseq=True))

        return cls._replace_scheme(parse.urlunsplit(url_parts), ws=True)

    def negotiate(self) -> None:
        negotiate_url = self._get_negotiate_url(
            self.connection.url
        )  # always use connection url, since transport url might have changed
        self.logger.debug("negotiate url: %s", negotiate_url)

        response = requests.post(negotiate_url, headers=self.connection.headers, verify=self.verify_ssl)
        self.logger.debug("response status code %d", response.status_code)

        if response.status_code != 200:
            if response.status_code == 401:
                raise UnauthorizedHubError(response=response)

            raise HubError(response=response)

        data = response.json()

        connection_id = data.get("connectionId")
        url = data.get("url")
        access_token = data.get("accessToken")

        if connection_id:
            self.url = self.encode_connection_id(
                self.url,
                connection_id,
            )
        elif url and access_token:
            self.logger.debug("azure url, reformat headers, token and url %r", data)
            self.url = self._replace_scheme(url, ws=True)
            token = data["accessToken"]
            self.connection.headers = {"Authorization": f"Bearer {token}"}

    def evaluate_handshake(self, message: Any) -> list[BaseMessage]:
        self.logger.debug("Evaluating handshake %s", message)
        msg, messages = self.connection.protocol.decode_handshake(message)

        if msg.error is None or msg.error == "":
            self.handshake_received = True
            self.state = ConnectionState.connected
            if self.connection.reconnection_handler is not None:
                self.connection.reconnection_handler.reconnecting = False
                if not self.connection_checker.running:
                    self.connection_checker.start()
        else:
            self.logger.error("failed to evaluate handshake: %r", msg.error)
            self.on_socket_error(self.ws, msg.error)
            self.stop()
            self.state = ConnectionState.disconnected

        return messages

    def on_open(self, _: websocket.WebSocketApp) -> None:
        msg = self.connection.protocol.handshake_message()
        self.send(msg)

    def on_close(self, callback: Callable[[], None], close_status_code: int | None, close_reason: str | None) -> None:
        self.logger.debug("websocket close: %r - %r", close_status_code, close_reason)
        self.state = ConnectionState.disconnected
        if callable(self._on_close):
            self._on_close()

        if callback is not None and callable(callback):
            callback()

    def on_reconnect(self):
        self.logger.debug("websocket reconnect")
        self.state = ConnectionState.disconnected
        if self._on_close is not None and callable(self._on_close):
            self._on_close()

    def on_socket_error(self, _: websocket.WebSocketApp, error: Any) -> None:
        """
        Args:
            _: Required to support websocket-client version equal or greater than 0.58.0
            error ([type]): [description]

        Raises:
            HubError: [description]
        """
        self.logger.error(error, exc_info=sys.exc_info())
        if callable(self._on_close):
            self._on_close()
        self.state = ConnectionState.disconnected

    def on_message(self, _app: websocket.WebSocketApp, raw_message: Any) -> None:
        self.logger.debug("message received: %r", raw_message)
        if not self.handshake_received:
            messages = self.evaluate_handshake(raw_message)
            if callable(self._on_open):
                self.state = ConnectionState.connected
                self._on_open()
        else:
            messages = self.connection.protocol.parse_messages(raw_message)

        if callable(self.connection.on_message):
            self.connection.on_message(messages)

    def send(self, message: BaseMessage) -> None:
        self.logger.debug("sending message: %r", message)
        try:
            self.ws.send(
                self.connection.protocol.encode(message),
                opcode=self.opcode,
            )
            self.connection_checker.last_message = time()
            if self.connection.reconnection_handler is not None:
                self.connection.reconnection_handler.reset()
        except (
            websocket._exceptions.WebSocketConnectionClosedException,
            OSError,
        ) as e:
            self.handshake_received = False
            self.logger.warning("connection closed")
            self.state = ConnectionState.disconnected
            if self.connection.reconnection_handler is None:
                if self._on_close is not None and callable(self._on_close):
                    self._on_close()
                raise ValueError(str(e))
            # Connection closed
            self.handle_reconnect()
        except Exception:
            raise

    def handle_reconnect(self):
        if not self.connection.reconnection_handler.reconnecting and callable(self._on_reconnect):
            self._on_reconnect()

        self.connection.reconnection_handler.reconnecting = True

        try:
            try:
                self.connection.stop()
            except websocket._exceptions.WebSocketConnectionClosedException:
                self.state = ConnectionState.disconnected

            self._greenlet.kill(block=True, timeout=10)

            self.logger.debug("reconnecting")
            self.handshake_received = False
            self.connection.start()
            self.logger.debug("reconnected")
        except Exception:
            self.logger.exception("reconnect failed, starting deferred reconnect")
            sleep_time = self.connection.reconnection_handler.next()
            gevent.spawn(self.deferred_reconnect, sleep_time)

    def deferred_reconnect(self, sleep_time):
        try:
            gevent.sleep(sleep_time)
            if not self.connection_alive:
                self.send(PingMessage())
        except Exception:
            self.logger.error("failed to send ping")
            self.connection.reconnection_handler.reconnecting = False
            self.connection_alive = False
