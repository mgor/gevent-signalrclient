from __future__ import annotations

from signalrcore.messages.subject import Subject

from typing import TYPE_CHECKING

from test.base_test_case import BaseTestCase, Urls

if TYPE_CHECKING:
    from signalrcore.connection import Connection


class TestClientStreamMethod(BaseTestCase):
    def test_stream(self):
        self.complete = False
        self.items = list(range(0,10))
        subject = Subject()
        self.connection.send("UploadStream", subject)
        while(len(self.items) > 0):
            subject.next(str(self.items.pop()))
        subject.complete()
        self.assertTrue(len(self.items) == 0)


class TestClientStreamMethodMsgPack(TestClientStreamMethod):
    def get_connection(self, _msgpack: bool = False) -> Connection:
        return super().get_connection(msgpack=True)


class TestClientNosslStreamMethodMsgPack(TestClientStreamMethodMsgPack):
    server_url = Urls.server_url_no_ssl


class TestClientNosslStreamMethod(TestClientStreamMethod):
    server_url = Urls.server_url_no_ssl
