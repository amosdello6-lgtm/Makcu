# 05 — Stock Firmware Findings (empirical)

Everything in this doc is what we saw on real hardware, not what a
datasheet said or a client library claimed. Where the observed behavior
disagrees with anyone's docs, this doc is right.

The unit under test:

- Enumerates on Windows as `USB-Enhanced-SERIAL CH343 (COM3)`.
- USB descriptor: `VID 0x1A86 / PID 0x55D3` (WCH CH343 USB-UART bridge).
- Default UART baud rate: **115200**.

## The chip inside

Confirmed by a boot log dumped when the firmware crash-rebooted on
`km.move(1, 0)` with no attached mouse:

| Field                  | Value                              |
| ---------------------- | ---------------------------------- |
| Chip                   | ESP32-S3, revision v0.2            |
| CPU                    | 240 MHz, multicore                 |
| ESP-IDF                | v5.4.1                             |
| App name in image      | `project-name` (default; unchanged)|
| App version            | 1                                  |
| Compile date           | May 4 2025 15:00:57                |
| Flash chip vendor      | Boya                               |
| Flash IO mode          | DIO                                |
| RAM regions            | ~256 KiB + 21 KiB + 32 KiB DRAM    |
| Persistent config      | NVS partition `config`, key `baud_rate` |
| GPIO0                  | input, pull-up, interrupt on both edges (BOOT button) |
| GPIO9                  | output (likely LED)                |

## The firmware banner

```
***********************
MAKCU 2024-2025,
Designer: .ihack
www.makcu.com
firmware version: 3.2.0
***********************
```

## Wire-level protocol

- Line ending accepted from host: `\r\n`.
- Reply line endings are inconsistent (see table below). Client code
  must not assume one format — it should read until the `>>> ` prompt
  and then split the buffer.
- End-of-reply marker: literal ASCII **`>>> `** (with trailing space).
- Unknown commands are silently ignored. There is no error reply.
- Zero-arg commands sometimes work bare (`km.version`) and sometimes
  require `()` (`km.buttons()` works, `km.buttons` doesn't). Rule of
  thumb: **always send with `()`**.

### Commands confirmed on hardware

| Command          | Reply payload (excluding `>>> `)                         | Notes                                                |
| ---------------- | ---------------------------------------------------------- | ---------------------------------------------------- |
| `km.version`     | `km.MAKCU\r\n`                                             | Device name, not a version number. Useless in v3.2.0.|
| `km.version()`   | `km.MAKCU\r\n`                                             | Same.                                                |
| `km.serial()`    | `km.Mouse does not have a serial number\n\r\n`             | Queries the *attached mouse's* USB serial, not the MAKCU's. |
| `km.buttons()`   | `km.buttons()\n<mask>\r\n`                                 | `<mask>` is a decimal integer. Command echoed on its own line first. |
| `km.move(x, y)`  | (with no mouse attached) → **firmware panic + reboot**     | Full ESP-IDF boot log then dumps out. See known-bad section. |
| `km.wheel(0)`    | Consumed the trailing boot log after the crash — unclear.  | Retest with a mouse attached.                        |

### Commands that were silent (unknown / not in v3.2.0)

`km.hw`, `km.hw()`, `km.chip`, `km.chip()`, `km.name`, `km.name()`,
`km.uid`, `km.uid()`, `km.info`, `km.info()`, `km.help`, `km.help()`,
`help`, `km.mouse`, `km.mouse()`, `km.status`, `km.status()`,
`km.locks`, `km.locks()`, `km.echo`, `km.echo()`, `km.buttons`,
`km.serial`.

### Commands we haven't tested yet (planned)

- `km.baud(<n>)` — likely present since NVS stores a `baud_rate` key.
- `km.left(0|1)`, `km.right(0|1)`, `km.middle(0|1)`, `km.side1(...)`,
  `km.side2(...)` — button injection.
- `km.click(...)` — combined press/release.
- `km.echo(0|1)` — toggle command echo in replies. Not confirmed.

## Known-bad behavior we should not copy

- **Crash on `km.move` with no attached mouse.** Almost certainly a
  null-pointer deref on the passthrough side. Our firmware must reject
  the command with `err:nomouse` (or similar) instead of panicking.
- **Silent drop of unknown commands.** Makes debugging host code painful.
  Our firmware should reply `err:unknown` with the offending name.
- **Inconsistent reply framing.** Command echo appears on some replies
  and not others. Ours should be one consistent shape.
- **Version command returns the device name, not a version.** The
  firmware banner has "3.2.0" but the queryable command doesn't. Ours
  should return a real version string.

## Recovery / flashing implications

Because the CH343 is on the ESP32-S3's UART programming pins (that's why
it enumerates a COM port), esptool *can* flash the S3 through it — but
the CH343's DTR/RTS lines aren't wired to GPIO0/EN, so esptool can't
auto-enter download mode. We have to do it by hand:

1. Hold GPIO0 (BOOT button) low.
2. Toggle EN (RESET) low → high, or unplug/replug USB power.
3. Release BOOT.
4. Run `esptool` — now it will connect.

We still need eyes on the PCB to find those buttons or pads. Once we
have physical BOOT access we can:

- Read the whole 4 MB flash to `stock-firmware.bin` for backup.
- Then flash our own firmware, knowing we can restore any time.
