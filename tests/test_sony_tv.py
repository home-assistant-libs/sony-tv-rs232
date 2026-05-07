"""Integration-ish tests for the SonyTV controller using the mock serial."""

from __future__ import annotations

import pytest

from sony_tv_rs232 import (
    AnswerCode,
    CommandError,
    InputSource,
    PictureMode,
    PowerState,
    WideMode,
)

from conftest import ack, reply


async def test_connect_does_not_query(tv, mock_serial) -> None:
    """connect() should NOT verify with a power query (Sony has no canonical ping)."""
    assert tv.connected
    # state.power is None until something is sent
    assert tv.state.power is None
    assert mock_serial.written == []


async def test_power_on_sets_state(tv, mock_serial) -> None:
    # Default conftest auto-acks any 8C-set
    await tv.power_on()
    assert tv.state.power is PowerState.ON
    assert b"\x8c\x00\x00\x02\x01\x8f" in mock_serial.written


async def test_power_off_sets_state(tv, mock_serial) -> None:
    await tv.power_off()
    assert tv.state.power is PowerState.OFF
    assert b"\x8c\x00\x00\x02\x00\x8e" in mock_serial.written


async def test_query_power_on(tv) -> None:
    """conftest pre-loads a power query reply showing power on."""
    power = await tv.query_power()
    assert power is PowerState.ON
    assert tv.state.power is PowerState.ON


async def test_query_power_off(tv, mock_serial) -> None:
    mock_serial.responses[bytes.fromhex("83 00 00 ff ff 81")] = reply(b"\x00")
    power = await tv.query_power()
    assert power is PowerState.OFF


async def test_set_volume(tv, mock_serial) -> None:
    await tv.set_volume(30)
    # 8C 00 05 03 01 1E B3
    assert b"\x8c\x00\x05\x03\x01\x1e\xb3" in mock_serial.written
    assert tv.state.volume == 30


async def test_query_volume(tv, mock_serial) -> None:
    # Real TV replies with [Direct=0x01, value] mirroring the Set shape
    mock_serial.responses[bytes.fromhex("83 00 05 ff ff 86")] = reply(b"\x01\x40")
    vol = await tv.query_volume()
    assert vol == 64


async def test_select_input_hdmi1(tv, mock_serial) -> None:
    await tv.select_input_source(InputSource.HDMI1)
    # 8C 00 02 03 04 01 96
    assert b"\x8c\x00\x02\x03\x04\x01\x96" in mock_serial.written
    assert tv.state.input_source is InputSource.HDMI1


async def test_select_input_hdmi2(tv, mock_serial) -> None:
    await tv.select_input_source(InputSource.HDMI2)
    assert tv.state.input_source is InputSource.HDMI2


async def test_select_input_tv(tv, mock_serial) -> None:
    """TV input has 1-byte data, not 2-byte."""
    await tv.select_input_source(InputSource.TV)
    assert b"\x8c\x00\x02\x02\x01\x91" in mock_serial.written


async def test_mute(tv, mock_serial) -> None:
    await tv.mute_on()
    assert tv.state.audio_mute is True
    await tv.mute_off()
    assert tv.state.audio_mute is False


async def test_set_picture_mode(tv, mock_serial) -> None:
    await tv.set_picture_mode(PictureMode.CINEMA)
    assert tv.state.picture_mode is PictureMode.CINEMA


async def test_set_wide_mode(tv, mock_serial) -> None:
    await tv.set_wide_mode(WideMode.NORMAL)
    assert tv.state.wide_mode is WideMode.NORMAL


async def test_subscribe(tv, mock_serial) -> None:
    received: list = []
    unsub = tv.subscribe(received.append)
    await tv.set_volume(50)
    assert received
    assert received[-1].volume == 50
    unsub()


async def test_command_error_raises(tv, mock_serial) -> None:
    """A non-zero answer code raises CommandError."""
    # Override the auto-ack: respond with Cancelled when setting volume.
    body = bytes([0x70, AnswerCode.CANCELED.value])
    cancel_ack = body + bytes([sum(body) & 0xFF])

    def handler(data: bytes) -> None:
        # Volume direct-set: 8C 00 05 03 01 ..
        if data[:5] == b"\x8c\x00\x05\x03\x01":
            mock_serial.feed(cancel_ack)
        else:
            mock_serial.feed(ack())

    mock_serial.command_handler = handler
    mock_serial.responses = {}

    with pytest.raises(CommandError):
        await tv.set_volume(50)


async def test_speaker_off(tv, mock_serial) -> None:
    await tv.speaker_off()
    assert tv.state.speaker_off is True
    await tv.speaker_on()
    assert tv.state.speaker_off is False


async def test_disconnect_notifies_subscribers(tv) -> None:
    received: list = []
    tv.subscribe(received.append)
    await tv.disconnect()
    assert received[-1] is None
    assert not tv.connected
