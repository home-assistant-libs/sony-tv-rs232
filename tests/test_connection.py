"""Serial connection failures at the public API boundary."""

from unittest.mock import patch

import pytest
import serialx
from conftest import NoHandshakeSonyTV

from sony_tv_rs232 import ConnectionLostError


async def test_connect_serial_exception_allows_retry(link) -> None:
    """An unavailable serial port raises the public error and can be retried."""
    tv = NoHandshakeSonyTV("esphome://proxy.local/?port_name=RS232")
    error = serialx.SerialException("Serial proxy is unavailable")
    reader, writer = await link.connect()

    with patch(
        "sony_tv_rs232.tv.serialx.open_serial_connection",
        side_effect=[error, (reader, writer)],
    ) as open_connection:
        with pytest.raises(
            ConnectionLostError, match="Serial proxy is unavailable"
        ) as exc_info:
            await tv.connect()

        assert exc_info.value.__cause__ is error
        assert not tv.connected

        try:
            await tv.connect()
            assert tv.connected
            assert open_connection.await_count == 2
        finally:
            await tv.disconnect()
