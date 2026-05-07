# sony-tv-rs232

Async Python library to control Sony Bravia TVs over RS232 serial.

## Project structure

```
src/sony_tv_rs232/
  __init__.py    -- Re-exports public API
  const.py       -- BAUD_RATE, COMMAND_TIMEOUT, header bytes, enums
                    (Function, InputSource, AnswerCode, PictureMode, ...)
  protocol.py    -- encode_control, encode_query, parse_answer, checksum
  state.py       -- TVState dataclass
  tv.py          -- SonyTV controller (connect / set / query / subscribe)
  __main__.py    -- CLI: python -m sony_tv_rs232 PORT [--power on|off|...] [--diagnose]

tests/
  conftest.py        -- MockSerialConnection fixture, ack/reply helpers
  test_protocol.py   -- encode/parse/percent helpers
  test_sony_tv.py    -- SonyTV behaviour against mock serial
```

## Architecture

- Built on `serialx` (`open_serial_connection`); supports any serialx URL —
  `/dev/ttyUSB0`, `socket://host:port`, `esphome://host/?port_name=TTL`, etc.
- All Sony Bravia TVs use **9600 baud, 8N1**, no flow control. Sony specifies
  a minimum 500 ms gap between commands; the controller enforces this via
  `INTER_COMMAND_DELAY`.
- Sony binary protocol (per the Pro Bravia Knowledge Center):
  - Set:         `[0x8C][0x00][Func][Length][Data...][Checksum]`
  - Query:       `[0x83][0x00][Func][0xFF][0xFF][Checksum]`
  - Set ack:     `[0x70][Status][Checksum]`            (3 bytes)
  - Query reply: `[0x70][Status][Size][Data...][Checksum]`
- `Length` (Set) and `Size` (reply) both count bytes that *follow* them,
  including the trailing checksum (so a 1-byte payload sets length=2).
- `Checksum` is `sum(preceding_bytes) & 0xFF`.
- The header byte distinguishes Set (`0x8C`) from Query (`0x83`).

## Key design decisions

- `connect()` only opens the port — Sony has no protocol-level "ping", so
  bad wiring / wrong baud surfaces as a `TimeoutError` on the first command.
- Each command method has a matching `set_*` and (where applicable)
  `query_*`. Sony's documented protocol is set-only on most consumer
  models; only Pro Bravia displays consistently honour query packets.
  `query_state()` therefore swallows TimeoutError/CommandError per attempt.
- State is updated **optimistically** on a successful Set ack and
  **authoritatively** when a Query reply arrives. Either path notifies
  subscribers via `_notify_subscribers`.
- The read loop pops the head of the pending queue to decide whether the
  next inbound packet is a 3-byte Set ack (`is_query=False`) or a longer
  Query reply (`is_query=True`); for query replies it reads the Size byte
  and uses it to size the rest of the packet.
- Sony's "Standby Command" function (`0x01`) must be Enabled while the TV
  is on if you ever want to Power ON it again from standby. Exposed as
  `enable_standby_listening()` / `disable_standby_listening()`.
- "Picture" on Sony menus is what other TVs call contrast; exposed as
  `set_picture_level()` / `state.picture_level` to avoid name clash with
  `set_picture_mode()`.

## Testing

- `pytest` with `pytest-asyncio`, `asyncio_mode = "auto"`.
- `MockSerialConnection` uses a real `asyncio.StreamReader` plus a mocked
  writer. `_on_write` synchronously feeds an ack into the reader: the
  default behaviour is to ack any `8C 00 ...` Set command with `70 00 70`
  unless the test pre-registers a specific reply via `mock_serial.responses`.
- `INTER_COMMAND_DELAY` is patched to 0 in tests to avoid real sleeps.
- Run: `uv run pytest`

## Protocol reference

- Pro Bravia Knowledge Center — Serial Control:
  <https://pro-bravia.sony.net/remote-display-control/serial-control/>
- Sony "RS-232C Protocol Manual" for KDL/KDS-XBR5 (consumer 2007 spec):
  <https://hf-files-oregon.s3.amazonaws.com/hdpjustaddpower_kb_attachments/2016/04-20/ab25a088-38d8-41a8-a136-fabda0005a1e/RS232_XBR5_protocol.pdf>

The XBR5 manual is set-only and describes only the 3-byte ack. The Pro
Bravia spec adds the `0x83` query header and the longer query-reply
shape.
