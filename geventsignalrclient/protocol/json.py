from __future__ import annotations

from geventsignalrclient.messages import BaseMessage, MessageType
from geventsignalrclient.protocol import BaseHubProtocol

import json
from typing import Any


class MyEncoder(json.JSONEncoder):
    # https://github.com/PyCQA/pylint/issues/414
    def default(self, o):
        if type(o) is MessageType:
            return o.value
        data = o.__dict__
        if "invocation_id" in data:
            data["invocationId"] = data["invocation_id"]
            del data["invocation_id"]
        if "stream_ids" in data:
            data["streamIds"] = data["stream_ids"]
            del data["stream_ids"]

        return data


class JsonHubProtocol(BaseHubProtocol):
    def __init__(self):
        super().__init__("json", 1, "Text", chr(0x1E))
        self.encoder = MyEncoder()

    def parse_messages(self, raw: str) -> list[BaseMessage]:
        raw_messages = [
            record.replace(self.record_separator, "")
            for record in raw.split(self.record_separator)
            if record is not None and record != ""
            and record != self.record_separator
        ]
        result = []
        for raw_message in raw_messages:
            dict_message = json.loads(raw_message)
            if len(dict_message.keys()) > 0:
                result.append(self.get_message(dict_message))

        return result

    def encode(self, message: Any) -> str:
        return self.encoder.encode(message) + self.record_separator
