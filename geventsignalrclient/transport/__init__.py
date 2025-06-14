from __future__ import annotations

from geventsignalrclient.messages import PingMessage
from geventsignalrclient.protocol import JsonHubProtocol

from abc import ABCMeta, abstractmethod
from collections.abc import Callable
from enum import Enum
from time import time
from typing import TYPE_CHECKING, TypedDict

import gevent

if TYPE_CHECKING:
    from geventsignalrclient.connection import Connection
    from geventsignalrclient.messages import BaseMessage

    from logging import Logger


class ConnectionState(Enum):
    connecting = 0
    connected = 1
    reconnecting = 2
    disconnected = 4


class ReconnectionType(Enum):
    raw = 0  # Reconnection with max reconnections and constant sleep time
    interval = 1  # variable sleep time


class ReconnectionParam(TypedDict, total=False):
    type: str
    keep_alive_interval: int
    reconnect_interval: int
    max_attempts: int
    intervals: list[int]


class BaseTransport(metaclass=ABCMeta):
    def __init__(
        self,
        connection: Connection,
        keep_alive_interval: int,
    ) -> None:
        self.connection = connection
        self.opcode: int = 0x1 if isinstance(self.connection.protocol, JsonHubProtocol) else 0x2
        self.connection_checker = ConnectionStateChecker(
            self.ping(),
            keep_alive_interval,
        )

        self._on_open: Callable[[], None] | None = None
        self._on_close: Callable[[], None] | None = None
        self._on_reconnect: Callable[[], None] | None = None

    @property
    def logger(self) -> Logger:
        return self.connection.logger

    def ping(self) -> Callable[[], None]:
        def wrapper() -> None:
            self.send(PingMessage())

        return wrapper

    def on_open_callback(self, callback: Callable[[], None] | None) -> None:
        self._on_open = callback

    def on_close_callback(self, callback: Callable[[], None] | None) -> None:
        self._on_close = callback

    def on_reconnect_callback(self, callback: Callable[[], None] | None) -> None:
        self._on_reconnect = callback

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def is_running(self) -> bool: ...

    @abstractmethod
    def send(self, message: BaseMessage) -> None: ...


class ConnectionStateChecker:
    def __init__(self, ping_function: Callable[[], None], keep_alive_interval: int, sleep: int = 1) -> None:
        self.sleep = sleep
        self.keep_alive_interval = keep_alive_interval
        self.last_message = time()
        self.ping_function = ping_function
        self.running: bool = False
        self._greenlet: gevent.Greenlet | None = None

    def start(self) -> None:
        self.running = True
        self._greenlet = gevent.spawn(self.run)

    def run(self) -> None:
        while self.running:
            gevent.sleep(self.sleep)
            time_without_messages = time() - self.last_message
            if self.keep_alive_interval < time_without_messages:
                self.ping_function()

    def stop(self) -> None:
        self.running = False


class ReconnectionHandler(metaclass=ABCMeta):
    def __init__(self) -> None:
        self.reconnecting: bool = False
        self.attempt_number: int = 0
        self.last_attempt: float = time()

    @abstractmethod
    def next(self) -> int: ...

    def reset(self) -> None:
        self.attempt_number = 0
        self.reconnecting = False


class RawReconnectionHandler(ReconnectionHandler):
    def __init__(self, sleep_time: int, max_attempts: int | None) -> None:
        super().__init__()
        self.sleep_time = sleep_time
        self.max_reconnection_attempts = max_attempts

    def next(self) -> int:
        self.reconnecting = True
        if self.max_reconnection_attempts is not None:
            if self.attempt_number <= self.max_reconnection_attempts:
                self.attempt_number += 1
                return self.sleep_time
            else:
                raise ValueError(f"max attemps reached {self.max_reconnection_attempts}")
        else:  # Infinite reconnect
            return self.sleep_time


class IntervalReconnectionHandler(ReconnectionHandler):
    def __init__(self, intervals: list[int]) -> None:
        super().__init__()
        self._intervals = intervals

    def next(self) -> int:
        self.reconnecting = True
        index = self.attempt_number
        self.attempt_number += 1

        try:
            return self._intervals[index]
        except IndexError:
            raise ValueError(f"max intervals reached {self._intervals}")
