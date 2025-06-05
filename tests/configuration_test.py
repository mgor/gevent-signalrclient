from __future__ import annotations

from geventsignalrclient.connection.builder import ConnectionBuilder

import logging

import websocket

from tests.helpers import BaseTestCase


class TestConfiguration(BaseTestCase):
    def test_bad_auth_function(self) -> None:
        with self.assertRaises(TypeError):
            ConnectionBuilder().with_url(
                self.server_url,
                options={
                    "verify_ssl": False,
                    "access_token_factory": 1234,
                    "headers": {"mycustomheader": "mycustomheadervalue"},
                },
            )

    def test_bad_url(self) -> None:
        with self.assertRaises(ValueError):
            ConnectionBuilder().with_url("")

    def test_bad_options(self) -> None:
        with self.assertRaises(TypeError):
            ConnectionBuilder().with_url(
                self.server_url,
                options=["ssl", True],  # type: ignore[arg-type]
            )

    def test_auth_configured(self) -> None:
        with self.assertRaises(TypeError):
            connection = ConnectionBuilder().with_url(
                self.server_url,
                options={
                    "verify_ssl": False,
                    "access_token_factory": "",
                    "headers": {"mycustomheader": "mycustomheadervalue"},
                },
            )
            connection.build()

    def test_enable_trace(self) -> None:
        connection = (
            ConnectionBuilder()
            .with_url(
                self.server_url,
                options={"verify_ssl": False},
            )
            .configure_logging(
                logging.WARNING,
                socket_trace=True,
            )
            .with_automatic_reconnect(
                {"type": "raw", "keep_alive_interval": 10, "reconnect_interval": 5, "max_attempts": 5}
            )
            .build()
        )
        connection.on_open(self.on_open)
        connection.on_close(self.on_close)
        connection.start()
        self.assertTrue(websocket.isEnabledForDebug())
        websocket.enableTrace(False)
        connection.stop()
