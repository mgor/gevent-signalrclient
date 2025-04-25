import websocket
import gevent
import traceback
import time
import ssl
import requests
from typing import Any
from .reconnection import ConnectionStateChecker
from .connection import ConnectionState
from ...messages.ping_message import PingMessage
from ...hub.errors import HubError, UnAuthorizedHubError
from ...protocol.messagepack_protocol import MessagePackHubProtocol
from ...messages.base_message import BaseMessage
from ..base_transport import BaseTransport
from ...helpers import Helpers
from signalrcore.transport.websockets.reconnection import ReconnectionHandler

class WebsocketTransport(BaseTransport):
    def __init__(self,
            url: str = "",
            headers: dict[str, str] | None = None,
            keep_alive_interval: int = 15,
            reconnection_handler: ReconnectionHandler | None = None,
            verify_ssl: bool = False,
            skip_negotiation: bool = False,
            enable_trace: bool = False,
            **kwargs: Any,
    ):
        super().__init__(**kwargs)

        self._ws: websocket.WebSocketApp | None = None
        self._greenlet: gevent.Greenlet | None = None

        self.enable_trace = enable_trace
        self.skip_negotiation = skip_negotiation
        self.url = url
        self.headers = dict() if headers is None else headers
        self.handshake_received = False
        self.token: str | None = None  # auth
        self._state: ConnectionState = ConnectionState.disconnected
        self.connection_alive: bool = False
        self.verify_ssl = verify_ssl
        self.connection_checker = ConnectionStateChecker(
            lambda: self.send(PingMessage()),
            keep_alive_interval
        )
        self.reconnection_handler = reconnection_handler

        if len(self.logger.handlers) > 0:
            websocket.enableTrace(self.enable_trace, self.logger.handlers[0])

    @property
    def state(self) -> ConnectionState:
        return self._state

    @state.setter
    def state(self, value: ConnectionState) -> None:
        from_value = self._state

        self.logger.debug('changed connection state from %r -> %r', from_value, value)

        self._state = value

    def is_running(self) -> bool:
        return self.state != ConnectionState.disconnected

    def stop(self) -> None:
        if self.state == ConnectionState.connected:
            self.connection_checker.stop()
            if self._ws is not None:
                self._ws.close()
            self.state = ConnectionState.disconnected
            self.handshake_received = False

    def start(self) -> bool:
        if not self.skip_negotiation:
            self.negotiate()

        if self.state == ConnectionState.connected:
            self.logger.warning("Already connected unable to start")
            return False

        self.state = ConnectionState.connecting
        self.logger.debug("start url:" + self.url)

        self._ws = websocket.WebSocketApp(
            self.url,
            header=self.headers,
            on_message=self.on_message,
            on_error=self.on_socket_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )

        self._greenlet = gevent.spawn(
            self._ws.run_forever,
            sslopt={"cert_reqs": ssl.CERT_NONE} if not self.verify_ssl else {},
        )

        return True

    def negotiate(self) -> None:
        negotiate_url = Helpers.get_negotiate_url(self.url)
        self.logger.debug("Negotiate url: {0}".format(negotiate_url))

        response = requests.post(negotiate_url, headers=self.headers, verify=self.verify_ssl)
        self.logger.debug("Response status code {0}".format(response.status_code))

        if response.status_code != 200:
            raise HubError(response.status_code) if response.status_code != 401 else UnAuthorizedHubError()

        data = response.json()

        connection_id = data.get('connectionId')
        url = data.get('url')
        access_token = data.get('accessToken')

        if connection_id:
            self.url = Helpers.encode_connection_id(
                self.url,
                connection_id,
            )
        elif url and access_token:
            Helpers.get_logger().debug(
                "Azure url, reformat headers, token and url {0}".format(data)
            )
            self.url = Helpers._replace_scheme(url, ws=True)
            self.token = data["accessToken"]
            self.headers = {"Authorization": f"Bearer {self.token}"}


    def evaluate_handshake(self, message) -> list[BaseMessage]:
        self.logger.debug("Evaluating handshake {0}".format(message))
        msg, messages = self.protocol.decode_handshake(message)
        if msg.error is None or msg.error == "":
            self.handshake_received = True
            self.state = ConnectionState.connected
            if self.reconnection_handler is not None:
                self.reconnection_handler.reconnecting = False
                if not self.connection_checker.running:
                    self.connection_checker.start()
        else:
            self.logger.error(msg.error)
            self.on_socket_error(self._ws, msg.error)
            self.stop()
            self.state = ConnectionState.disconnected

        return messages

    def on_open(self, _):
        self.logger.debug("-- web socket open --")
        msg = self.protocol.handshake_message()
        self.send(msg)

    def on_close(self, callback, close_status_code, close_reason):
        self.logger.debug("-- web socket close --")
        self.logger.debug(close_status_code)
        self.logger.debug(close_reason)
        self.state = ConnectionState.disconnected
        if self._on_close is not None and callable(self._on_close):
            self._on_close()

        if callback is not None and callable(callback):
            callback()

    def on_reconnect(self):
        self.logger.debug("-- web socket reconnecting --")
        self.state = ConnectionState.disconnected
        if self._on_close is not None and callable(self._on_close):
            self._on_close()

    def on_socket_error(self, app, error):
        """
        Args:
            _: Required to support websocket-client version equal or greater than 0.58.0
            error ([type]): [description]

        Raises:
            HubError: [description]
        """
        self.logger.debug("-- web socket error --")
        self.logger.error(traceback.format_exc(10, True))
        self.logger.error("{0} {1}".format(self, error))
        self.logger.error("{0} {1}".format(error, type(error)))
        self._on_close()
        self.state = ConnectionState.disconnected
        #raise HubError(error)

    def on_message(self, app, raw_message):
        self.logger.debug("Message received{0}".format(raw_message))
        if not self.handshake_received:
            messages = self.evaluate_handshake(raw_message)
            if self._on_open is not None and callable(self._on_open):
                self.state = ConnectionState.connected
                self._on_open()

            if len(messages) > 0:
                return self._on_message(messages)

            return []

        return self._on_message(
            self.protocol.parse_messages(raw_message))

    def send(self, message):
        self.logger.debug("Sending message {0}".format(message))
        try:
            self._ws.send(
                self.protocol.encode(message),
                opcode=0x2 if isinstance(self.protocol, MessagePackHubProtocol) else 0x1,
            )
            self.connection_checker.last_message = time.time()
            if self.reconnection_handler is not None:
                self.reconnection_handler.reset()
        except (
                websocket._exceptions.WebSocketConnectionClosedException,
                OSError,
        ) as ex:
            self.handshake_received = False
            self.logger.warning("Connection closed {0}".format(ex))
            self.state = ConnectionState.disconnected
            if self.reconnection_handler is None:
                if self._on_close is not None and\
                        callable(self._on_close):
                    self._on_close()
                raise ValueError(str(ex))
            # Connection closed
            self.handle_reconnect()
        except Exception as ex:
            raise ex

    def handle_reconnect(self):
        if not self.reconnection_handler.reconnecting and self._on_reconnect is not None and \
                callable(self._on_reconnect):
            self._on_reconnect()
        self.reconnection_handler.reconnecting = True
        try:
            self.stop()
            self.start()
        except Exception as ex:
            self.logger.error(ex)
            sleep_time = self.reconnection_handler.next()
            gevent.spawn(self.deferred_reconnect, sleep_time)

    def deferred_reconnect(self, sleep_time):
        gevent.sleep(sleep_time)
        try:
            if not self.connection_alive:
                self.send(PingMessage())
        except Exception as ex:
            self.logger.error(ex)
            self.reconnection_handler.reconnecting = False
            self.connection_alive = False
