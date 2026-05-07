# sony-tv-rs232

Async Python library to control Sony Bravia TVs over RS232 serial, built on
[serialx](https://github.com/puddly/serialx).

## Tested & verified models 
- K85XR90

## Installation

```bash
pip install sony-tv-rs232

# To talk to a TV over an ESPHome serial proxy:
pip install 'sony-tv-rs232[esphome]'
```

Requires Python 3.12+.

## Quick start

```python
import asyncio
from sony_tv_rs232 import SonyTV, InputSource

async def main():
    tv = SonyTV("/dev/ttyUSB0")
    await tv.connect()

    # Many models reply to queries; some don't. query_state() will skip
    # any function the TV doesn't ack.
    await tv.query_state()
    print(f"Power:  {tv.state.power}")
    print(f"Input:  {tv.state.input_source}")
    print(f"Volume: {tv.state.volume}%")

    await tv.set_volume(20)
    await tv.select_input_source(InputSource.HDMI1)

    await tv.disconnect()

asyncio.run(main())
```

## CLI

A built-in CLI lets you quickly test your serial connection:

```bash
# Query and print TV status (works on models that honour Get requests)
python -m sony_tv_rs232 /dev/ttyUSB0

# Talk to a TV via an ESPHome serial proxy ("TTL" port)
python -m sony_tv_rs232 'esphome://192.168.1.29/?port_name=TTL'

# Talk to a TV over a raw TCP socket (e.g. ser2net)
python -m sony_tv_rs232 socket://192.168.1.29:5000

# Single-shot actions
python -m sony_tv_rs232 /dev/ttyUSB0 --power on
python -m sony_tv_rs232 /dev/ttyUSB0 --power off
python -m sony_tv_rs232 /dev/ttyUSB0 --input HDMI2
python -m sony_tv_rs232 /dev/ttyUSB0 --volume 30
python -m sony_tv_rs232 /dev/ttyUSB0 --mute on
python -m sony_tv_rs232 /dev/ttyUSB0 --wide NORMAL
python -m sony_tv_rs232 /dev/ttyUSB0 --picture-mode CINEMA
python -m sony_tv_rs232 /dev/ttyUSB0 --display
```

## Features

### Full state after query

`connect()` only opens the serial port. Sony's protocol has no canonical
"ping" command, so connection problems surface on the first command rather
than at connect time. Call `query_state()` to populate the current TV state
into `tv.state`.

```python
tv = SonyTV("/dev/ttyUSB0")
await tv.connect()
await tv.query_state()

state = tv.state
state.power           # PowerState.ON / PowerState.OFF
state.input_source    # InputSource enum
state.volume          # 0..100 percent
state.audio_mute      # bool
state.picture_mode    # PictureMode enum
state.wide_mode       # WideMode enum
# ...etc
```

> **Note:** Sony's documented protocol is set-only on most consumer
> Bravia TVs — only Pro Bravia / B2B displays consistently honour Get
> requests. `query_state()` silently skips any function the TV doesn't
> answer; state is otherwise updated optimistically when each Set command
> is acknowledged.

### Event subscription

Subscribe to state changes to react in real-time. Callbacks receive a
`TVState` snapshot, or `None` when the connection is lost.

```python
def on_state_change(state):
    if state is None:
        print("Disconnected!")
        return
    print(f"Volume: {state.volume}%, Source: {state.input_source}")

unsub = tv.subscribe(on_state_change)
# Later:
unsub()
```

### Power

Sony's quirk: while the TV is in standby it will **only** accept Power ON
if the "Standby Command" was previously Enabled. Call
`enable_standby_listening()` once while the TV is on, then Power ON works
later from standby.

```python
await tv.enable_standby_listening()  # arm the TV (do this once, while on)
await tv.power_off()                 # to standby
await tv.power_on()                  # works because standby listening was enabled
power = await tv.query_power()       # PowerState.ON / PowerState.OFF
```

### Input source

```python
from sony_tv_rs232 import InputSource

await tv.select_input_source(InputSource.HDMI1)
source = await tv.query_input_source()  # InputSource enum

await tv.select_next_input_source()  # cycle (same as remote's INPUT key)
```

Available sources: `TV`, `VIDEO1`-`3`, `COMPONENT1`-`2`, `HDMI1`-`4`,
`PC`. (`HDMI4` and `PC` are SXRD-only on most models.)

### Volume / mute

```python
await tv.set_volume(30)       # 0..100
await tv.volume_up()
await tv.volume_down()
await tv.mute_on()
await tv.mute_off()
await tv.mute_toggle()
volume = await tv.query_volume()  # int 0..100
muted = await tv.query_mute()     # True if muted
```

### Picture controls

All on a 0..100 scale.

```python
await tv.set_picture_level(70)  # "Picture" in Sony menus = contrast
await tv.set_brightness(50)
await tv.set_color(50)
await tv.set_sharpness(50)
await tv.set_hue(50, 50)        # red-bias, green-bias
```

### Audio controls

```python
await tv.set_treble(50)
await tv.set_bass(50)
await tv.speaker_on()
await tv.speaker_off()  # mute internal speakers (e.g. with external receiver)
```

### Modes

```python
from sony_tv_rs232 import (
    AdvancedIris, CineMotion, Mode4_3, PictureMode, SoundMode, WideMode,
)

await tv.set_picture_mode(PictureMode.CINEMA)
await tv.set_sound_mode(SoundMode.STANDARD)
await tv.set_wide_mode(WideMode.NORMAL)
await tv.set_4_3_mode(Mode4_3.NORMAL)
await tv.set_cine_motion(CineMotion.AUTO_1)
await tv.set_advanced_iris(AdvancedIris.AUTO_1)  # SXRD only
```

### Display / closed caption / sleep timer

```python
from sony_tv_rs232 import ClosedCaption, OffTimer

await tv.toggle_display()  # same as the remote's INFO key

await tv.set_closed_caption(ClosedCaption.OFF)
await tv.set_closed_caption(ClosedCaption.DIGITAL_SERVICE1)

await tv.set_off_timer(OffTimer.MIN_60)
await tv.set_off_timer(OffTimer.OFF)
```

### Connection handling

- `connect()` only opens the port — there is no protocol-level "ping",
  so wiring/bus errors surface on the first command via `TimeoutError`.
- If the serial connection is lost, subscribers receive `None` and
  `connected` becomes `False`.
- Commands return an `Answer`; any non-`Completed` status raises
  `CommandError`.

```python
from sony_tv_rs232 import CommandError

try:
    await tv.set_volume(50)
except TimeoutError:
    print("TV not responding")
except CommandError as err:
    print(f"TV rejected command: {err}")
```

## Serial connection

The library uses [serialx](https://github.com/puddly/serialx). Sony Bravia
TVs use **9600 baud, 8 data bits, no parity, 1 stop bit**, no flow control.

Most Bravia TVs use a DE-9 male connector (requires a null-modem cable).
Some sets expose RS232 on a 3.5mm phone jack instead. The library accepts
any serialx-compatible URL:

| URL form                                           | Use case                            |
| -------------------------------------------------- | ----------------------------------- |
| `/dev/ttyUSB0`                                     | local USB-serial adapter            |
| `socket://host:port`                               | raw TCP serial bridge (ser2net)     |
| `esphome://host/?port_name=TTL`                    | ESPHome serial proxy component      |
| `esphome://host/?port_name=RS-232`                 | ESPHome serial proxy component      |

Sony recommends a minimum 500 ms gap between commands; the library
enforces this internally.

## Protocol

Sony Bravia TVs use a binary, length-prefixed protocol:

```
Set:        [0x8C][0x00][Func][Length][Data...][Checksum]
            e.g. 8C 00 00 02 01 8F  (set power on)

Query:      [0x83][0x00][Func][0xFF][0xFF][Checksum]
            e.g. 83 00 00 FF FF 81  (query power)

Set ack:    [0x70][Status][Checksum]
            e.g. 70 00 70           (Completed)

Query reply: [0x70][Status][Size][Data...][Checksum]
            e.g. 70 00 02 01 73     (Completed; data=01 -> power on)
```

`Length` and `Size` count the bytes that follow them, including the
trailing checksum. `Checksum` is the lower byte of the sum of every
preceding byte.

Status codes: `0x00` Completed, `0x01` Limit Over (max), `0x02` Limit
Over (min), `0x03` Cancelled, `0x04` Parse Error.

## Development

```bash
# Install dev dependencies
uv sync

# Run tests
uv run pytest
```

## License

MIT
