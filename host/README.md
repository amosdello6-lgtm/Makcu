# host/ — Python client for MAKCU

A minimal, readable Python client that talks to the MAKCU's stock
firmware over its CH343 UART. Zero dependencies beyond `pyserial`.

This targets the *stock* firmware protocol as observed empirically (see
`docs/05-stock-firmware.md`). When we replace the firmware later, this
package will grow a v1 client for the new protocol without losing the
v0 one — same package, different classes.

## Install (from a checkout)

```
py -m pip install -e .\host
```

Or just add `host/` to `PYTHONPATH` and import — the example script does
that automatically.

## Quick start

```python
from makcu_host import Makcu, NoMouseAttached

with Makcu("COM3") as mkc:
    print(mkc.name())              # -> 'MAKCU'
    print(mkc.buttons())            # -> 0
    print(mkc.mouse_serial())       # -> None (no mouse in port) or serial string

    try:
        mkc.move(50, 0)             # slide cursor 50px right
        mkc.click_left()            # press+release
    except NoMouseAttached:
        # Stock v3.2.0 crash-reboots on move/click when no passthrough
        # mouse is plugged into the MAKCU. The client detects the reboot
        # signature and raises this instead of leaving you guessing.
        print("plug a mouse into the MAKCU first")
```

## Available methods (v0)

| Method                       | Wire command       | Notes                                     |
| ---------------------------- | ------------------ | ----------------------------------------- |
| `name()`                     | `km.version()`     | Returns `'MAKCU'` on stock v3.2.0.        |
| `buttons()`                  | `km.buttons()`     | Returns int bitmask of currently held buttons. |
| `mouse_serial()`             | `km.serial()`      | USB serial of the attached mouse, or None. |
| `move(dx, dy)`               | `km.move(dx, dy)`  | Needs an attached mouse. Raises `NoMouseAttached` otherwise. |
| `wheel(delta)`               | `km.wheel(delta)`  | Not fully validated yet.                  |
| `press_left/right/middle`    | `km.left(1)` etc.  | Uncached; each call is a round-trip.      |
| `release_left/right/middle`  | `km.left(0)` etc.  |                                           |
| `click_left(hold_ms=30)`     | press → sleep → release | Host-side timing.                    |
| `raw(cmd)`                   | *anything*         | Escape hatch — returns the reply text.    |
| `firmware_banner()`          | (drains buffer)    | Read pending boot banner. Blank if none.  |

## Example

```
py host\makcu_host\examples\hello.py COM3
```

Prints identity + button state and attempts a small move.
