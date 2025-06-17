from __future__ import annotations

from geventsignalrclient.connection import ConnectionBuilder
from geventsignalrclient.messages import CompletionMessage
from geventsignalrclient.protocol import MessagePackHubProtocol

import logging
import uuid
from itertools import product
from typing import Any

import pytest
import requests
from gevent.lock import Semaphore
from pytest_mock.plugin import MockerFixture

from tests.helpers import SOME, access_token_factory, release


@pytest.mark.parametrize("transport,data", product(["https", "http"], ["json", "msgpack"]))
def test_send_hub_error(mocker: MockerFixture, signalr_server: str, transport: str, data: str) -> None:
    protocol = "wss" if transport == "https" else "ws"
    port = 443 if transport == "https" else 80
    server_url = f"{protocol}://{signalr_server}:{port}/chatHub"
    builder = ConnectionBuilder().with_url(
        server_url,
        options={
            "verify_ssl": False,
        },
    )

    if data == "msgpack":
        builder.with_hub_protocol(MessagePackHubProtocol())

    builder.configure_logging(
        logging.WARNING,
    ).with_automatic_reconnect(
        {
            "type": "raw",
            "keep_alive_interval": 10,
            "reconnect_interval": 5,
            "max_attempts": 5,
        }
    )
    connection = builder.build()

    lock = Semaphore()

    def on_error(*_args: Any, **_kwargs: Any) -> None:
        release(lock)()

    def on_message(*args: Any, **kwargs: Any) -> None:
        release(lock)()
        lock.acquire(timeout=10)

    on_error_spy = mocker.Mock(wraps=on_error)
    on_message_spy = mocker.Mock(wraps=on_message)

    connection.on_open(release(lock))
    connection.on_close(release(lock))
    connection.on_error(on_error_spy)
    connection.on("ThrowExceptionCall", on_message_spy)

    assert lock.acquire(timeout=10)

    connection.start()

    assert lock.acquire(timeout=10)

    connection.send("ThrowException", ["error message"])

    assert lock.acquire(timeout=10)

    connection.stop()

    assert lock.acquire(timeout=10)

    on_message_spy.assert_called_once_with(["error message"])
    on_error_spy.assert_called_once_with(
        SOME(
            CompletionMessage,
            result=None,
            error="An unexpected error occurred invoking 'ThrowException' on the server.",
        )
    )


@pytest.mark.parametrize("transport,data", product(["https", "http"], ["json", "msgpack"]))
def test_send_with_invocation(mocker: MockerFixture, signalr_server: str, transport: str, data: str) -> None:
    protocol = "wss" if transport == "https" else "ws"
    port = 443 if transport == "https" else 80
    server_url = f"{protocol}://{signalr_server}:{port}/chatHub"
    builder = ConnectionBuilder().with_url(
        server_url,
        options={
            "verify_ssl": False,
        },
    )

    if data == "msgpack":
        builder.with_hub_protocol(MessagePackHubProtocol())

    builder.configure_logging(
        logging.WARNING,
    ).with_automatic_reconnect(
        {
            "type": "raw",
            "keep_alive_interval": 10,
            "reconnect_interval": 5,
            "max_attempts": 5,
        }
    )
    connection = builder.build()

    lock = Semaphore()

    def on_invocation(*_args: Any, **_kwargs: Any) -> None:
        release(lock)()

    def on_message(*_args: Any, **_kwargs: Any) -> None:
        release(lock)()
        lock.acquire(timeout=10)

    on_invocation_spy = mocker.Mock(wraps=on_invocation)
    on_message_spy = mocker.Mock(wraps=on_message)

    connection.on_open(release(lock))
    connection.on_close(release(lock))
    connection.on("ReceiveMessage", on_message_spy)

    assert lock.acquire(timeout=10)

    connection.start()

    assert lock.acquire(timeout=10)

    connection.send("SendMessage", ["foobar", "hello world!"], on_invocation_spy)

    assert lock.acquire(timeout=10)

    connection.stop()

    assert lock.acquire(timeout=10)

    on_invocation_spy.assert_called_once_with(SOME(CompletionMessage, result=None, error=None))
    on_message_spy.assert_called_once_with(["foobar", "hello world!"])


@pytest.mark.parametrize("transport,data", product(["https", "http"], ["json", "msgpack"]))
def test_send_auth(mocker: MockerFixture, signalr_server: str, transport: str, data: str) -> None:
    protocol = "wss" if transport == "https" else "ws"
    port = 443 if transport == "https" else 80
    server_url = f"{protocol}://{signalr_server}:{port}/authHub"
    builder = ConnectionBuilder().with_url(
        server_url,
        options={
            "verify_ssl": False,
            "access_token_factory": access_token_factory(
                signalr_server, protocol=transport, username="test", password="test"
            ),
            "headers": {"mycustomheader": "mycustomheadervalue"},
        },
    )

    if data == "msgpack":
        builder.with_hub_protocol(MessagePackHubProtocol())

    builder.configure_logging(
        logging.WARNING,
    ).with_automatic_reconnect(
        {
            "type": "raw",
            "keep_alive_interval": 10,
            "reconnect_interval": 5,
            "max_attempts": 5,
        }
    )

    lock = Semaphore()
    message = f"new message {uuid.uuid4()}"

    def on_receive_message(*_args: Any, **_kwargs: Any) -> None:
        release(lock)()

    on_receive_message_spy = mocker.Mock(wraps=on_receive_message)

    connection = builder.build()
    connection.on("ReceiveMessage", on_receive_message_spy)
    connection.on_open(release(lock))
    connection.on_close(release(lock))

    assert lock.acquire(timeout=30)

    connection.start()

    assert lock.acquire(timeout=30)

    connection.send("SendMessage", [message])
    assert lock.acquire(timeout=30)

    connection.stop()

    on_receive_message_spy.assert_called_once_with([message])


@pytest.mark.parametrize("transport,data", product(["https", "http"], ["json", "msgpack"]))
def test_send_auth_error(signalr_server: str, transport: str, data: str) -> None:
    protocol = "wss" if transport == "https" else "ws"
    server_url = f"{protocol}://{signalr_server}:5001/authHub"

    builder = ConnectionBuilder().with_url(
        server_url,
        options={
            "verify_ssl": False,
            "access_token_factory": access_token_factory(
                signalr_server, protocol=transport, username="test", password="ff"
            ),
        },
    )

    if data == "msgpack":
        builder.with_hub_protocol(MessagePackHubProtocol())

    builder.configure_logging(logging.ERROR)
    connection = builder.build()

    with pytest.raises(requests.exceptions.ConnectionError):
        connection.start()
