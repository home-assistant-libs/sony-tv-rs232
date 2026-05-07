"""Shared test fixtures for sony_tv_rs232."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sony_tv_rs232
import sony_tv_rs232.tv as sony_tv_module
from sony_tv_rs232 import (
    AnswerCode,
    SonyTV,
    checksum,
)
from sony_tv_rs232.const import HEADER_ANSWER

# Speed up tests
sony_tv_rs232.COMMAND_TIMEOUT = 0.1
sony_tv_module.COMMAND_TIMEOUT = 0.1
sony_tv_module.INTER_COMMAND_DELAY = 0.0


def ack(code: AnswerCode = AnswerCode.COMPLETED) -> bytes:
    """Build a 3-byte Set-ack packet from the TV."""
    body = bytes([HEADER_ANSWER, code.value])
    return body + bytes([checksum(body)])


def reply(data: bytes, code: AnswerCode = AnswerCode.COMPLETED) -> bytes:
    """Build a query-reply packet [0x70][code][size][...data][cs] from the TV.

    ``size`` is the count of bytes after the size byte (data + checksum).
    """
    size = len(data) + 1
    body = bytes([HEADER_ANSWER, code.value, size]) + data
    return body + bytes([checksum(body)])


# Maps the exact bytes the host writes to the bytes the mock TV should
# reply with.
DEFAULT_RESPONSES: dict[bytes, bytes] = {
    # Power query 83 00 00 FF FF 81 -> reply 70 00 02 01 73 (power on)
    bytes.fromhex("83 00 00 ff ff 81".replace(" ", "")): reply(b"\x01"),
}


class MockSerialConnection:
    """Mock serial reader/writer pair with auto-response support."""

    def __init__(self) -> None:
        self.reader = asyncio.StreamReader()
        self.writer = MagicMock()
        self.writer.write = MagicMock()
        self.writer.drain = AsyncMock()
        self.writer.close = MagicMock()
        self.writer.wait_closed = AsyncMock()
        self.written: list[bytes] = []
        self.responses: dict[bytes, bytes] = {}
        self.command_handler: Callable[[bytes], None] | None = None
        self.writer.write.side_effect = self._on_write

    def _on_write(self, data: bytes) -> None:
        self.written.append(data)
        if data in self.responses:
            self.feed(self.responses[data])
        elif self.command_handler is not None:
            self.command_handler(data)
        else:
            # Default: ack any Set command (header 8C, category 00)
            if len(data) >= 2 and data[0] == 0x8C and data[1] == 0x00:
                self.feed(ack())

    def feed(self, packet: bytes) -> None:
        """Inject raw bytes into the reader."""
        self.reader.feed_data(packet)


@pytest.fixture
async def mock_serial() -> MockSerialConnection:
    return MockSerialConnection()


@pytest.fixture
async def tv(mock_serial: MockSerialConnection):
    """Create a connected SonyTV with mocked serial."""
    tv = SonyTV("/dev/ttyUSB0")
    mock_serial.responses = dict(DEFAULT_RESPONSES)

    async def fake_open(*args, **kwargs):
        return mock_serial.reader, mock_serial.writer

    with patch(
        "sony_tv_rs232.tv.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        await tv.connect()

    yield tv

    if tv.connected:
        await tv.disconnect()
