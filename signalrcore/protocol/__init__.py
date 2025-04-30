from __future__ import annotations

from signalrcore.messages import (
    BaseMessage,
    CancelInvocationMessage,  # 5
    CloseMessage,  # 7
    CompletionMessage,  # 3
    HandshakeRequestMessage,
    HandshakeResponseMessage,
    InvocationMessage,  # 1
    MessageType,
    PingMessage,  # 6
    StreamInvocationMessage,  # 4
    StreamItemMessage,  # 2
)

import json as pyjson
from abc import abstractmethod
from typing import Any


class BaseHubProtocol:
    def __init__(self, protocol: str, version: int, transfer_format: str, record_separator: str) -> None:
        self.protocol = protocol
        self.version = version
        self.transfer_format = transfer_format
        self.record_separator = record_separator

    @staticmethod
    def get_message(json_message: dict[str, Any]) -> BaseMessage:
        message_type =  MessageType.CLOSE if "type" not in json_message.keys() else MessageType(json_message["type"])

        json_message["invocation_id"] = json_message.get("invocationId", None)
        json_message["headers"] = json_message.get("headers")
        json_message["error"] = json_message.get("error")
        json_message["result"] = json_message.get("result")

        if message_type == MessageType.INVOCATION:
            return InvocationMessage(
                invocation_id=json_message.get('invocation_id'),
                headers=json_message.get('headers'),
                target=json_message['target'],
                arguments=json_message['arguments'],
            )
        elif message_type == MessageType.STREAM_ITEM:
            return StreamItemMessage(
                invocation_id=json_message['invocation_id'],
                headers=json_message.get('headers'),
                item=json_message['item'],
            )
        elif message_type == MessageType.COMPLETION:
            return CompletionMessage(
                invocation_id=json_message['invocation_id'],
                headers=json_message.get('headers'),
                result=json_message.get('result'),
                error=json_message.get('error'),
            )
        elif message_type == MessageType.STREAM_INVOCATION:
            return StreamInvocationMessage(
                invocation_id=json_message['invocation_id'],
                headers=json_message.get('headers'),
                target=json_message['target'],
                arguments=json_message['arguments'],
            )
        elif message_type == MessageType.CANCEL_INVOCATION:
            return CancelInvocationMessage(
                invocation_id=json_message['invocation_id'],
                headers=json_message.get('headers'),
            )
        elif message_type == MessageType.PING:
            return PingMessage()
        elif message_type is MessageType.CLOSE:
            return CloseMessage(
                error=json_message.get('error'),
            )

        message = f'unknown message type {message_type}'
        raise ValueError(message)

    def decode_handshake(self, raw_message: str) -> tuple[HandshakeResponseMessage, list[BaseMessage]]:
        messages = raw_message.split(self.record_separator)
        messages = list(filter(lambda x: x != "", messages))
        data = pyjson.loads(messages[0])
        idx = raw_message.index(self.record_separator)
        return HandshakeResponseMessage(data.get("error", None)), self.parse_messages(raw_message[idx + 1 :]) if len(messages) > 1 else []

    def handshake_message(self) -> HandshakeRequestMessage:
        return HandshakeRequestMessage(self.protocol, self.version)

    @abstractmethod
    def parse_messages(self, raw_message: str) -> list[BaseMessage]:
        ...

    @abstractmethod
    def encode(self, message: Any) -> str:
        ...

from .json import JsonHubProtocol
from .msgpack import MessagePackHubProtocol

__all__ = [
    'JsonHubProtocol',
    'MessagePackHubProtocol',
]
