# 03 — Serial Command Protocol (v0.1)

The command channel is a virtual serial port (USB CDC ACM). On the PC
side it shows up as `/dev/ttyACM*` on Linux, `/dev/tty.usbmodem*` on
macOS, or `COMx` on Windows.

## Framing

- ASCII, one command per line.
- Line terminator: `\n` (LF). `\r\n` also accepted (`\r` stripped).
- Any bytes between commands are ignored, so a bare `\n` is a no-op.
- Maximum line length: **256 bytes**. Anything longer is dropped and the
  device replies `err:overflow`.

## Baud rate

Irrelevant. CDC ACM is a virtual serial port — the "baud rate" is only
there because host libraries insist on setting one. Firmware ignores it.

## Reply model

Every command produces exactly one reply line. Replies never arrive
unsolicited — if the firmware has an event to report (button state
change, mouse detach), it queues it and only emits it after the *next*
command's reply, prefixed with `evt:`. This keeps the client's read loop
simple.

- Success (no value): `ok`
- Success with value: `<value>` (single line, ASCII)
- Error: `err:<code>`

Error codes:

| Code           | Meaning                                            |
| -------------- | -------------------------------------------------- |
| `syntax`       | Malformed command or bad argument type             |
| `range`        | Argument out of allowed range                      |
| `overflow`     | Line too long                                      |
| `unknown`      | Command name not recognised                        |
| `nomouse`      | Command needs the passthrough mouse; none attached |
| `busy`         | Device is mid-operation, retry                     |

## Commands

Names are chosen to match the de facto MAKCU protocol *for the subset
that's useful for learning*. Commands that only exist to defeat anti-
cheat (VID/PID spoofing, HID descriptor cloning) are deliberately
absent.

### Identity

- `km.version` → `<semver>`
- `km.hw` → `<board name>` (e.g. `esp32s3-devkitc-1`)
- `km.uptime` → `<milliseconds>`

### Relative motion

- `km.move(dx, dy)` → `ok`
  - `dx, dy` are int16, range `-32767..32767`. Larger moves are split
    across polling ticks internally so no report ever exceeds int8/int16
    range depending on descriptor mode.
- `km.move(dx, dy, ms)` → `ok`
  - Same, spread over `ms` milliseconds (1..10000). Firmware paces it.

### Wheel

- `km.wheel(delta)` → `ok`, `delta` int8 range.

### Buttons

- `km.left(1)` / `km.left(0)` → `ok` — press / release left button
- `km.right(1)` / `km.right(0)` → `ok`
- `km.middle(1)` / `km.middle(0)` → `ok`
- `km.side1(1|0)`, `km.side2(1|0)` → `ok` — extra mouse buttons
- `km.click(button)` → `ok` — press+release, `button ∈ {left,right,middle,side1,side2}`
  - Timing: 30 ms hold. Configurable via `km.click_ms(30)` later, not v0.

### State

- `km.buttons` → `<mask>` — current button state as a hex byte
  (`0x00..0xFF`, bit order: L, R, M, S1, S2, reserved…)
- `km.mouse` → `attached` or `detached`

### Locks (block real-mouse input on an axis or button)

Useful for debugging your host code without a real mouse fighting it.

- `km.lock_x(1|0)`, `km.lock_y(1|0)` → `ok`
- `km.lock_left(1|0)`, `km.lock_right(1|0)`, `km.lock_middle(1|0)` → `ok`
- `km.lock_wheel(1|0)` → `ok`
- `km.locks` → hex mask of active locks

### Housekeeping

- `km.help` → prints a compact list of all commands (multi-line, ends with
  a blank line — the one place we break the "one reply per command" rule)
- `km.reboot` → `ok` then reboots (host will see the CDC port disappear)

## Example session

```
> km.version
0.1.0
> km.mouse
attached
> km.move(200, 0)
ok
> km.click(left)
ok
> km.lock_x(1)
ok
> km.locks
0x01
> km.lock_x(0)
ok
```

## What we're NOT adding

- `km.serial(...)` / `km.spoof(...)` — any command that changes the
  advertised USB descriptors to impersonate a specific mouse. Out of
  scope for the same reason we picked a unique VID/PID.
- Human-jitter simulation on `move`. If you want curved paths, do it on
  the host side and stream a series of small `km.move` calls.

## Versioning

`km.version` returns SemVer. Backwards-incompatible protocol changes
bump the major. The Python client checks the major on connect and
refuses to run against a mismatched firmware.
