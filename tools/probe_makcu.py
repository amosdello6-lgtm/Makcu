"""Probe the MAKCU's stock firmware over the CH343 UART.

The CH343 in the MAKCU is only a USB-to-UART bridge. Whatever real chip is
inside listens on that UART for a text-based command protocol. This script
tries a handful of plausible baud rates and known MAKCU commands and prints
anything the device sends back, so we can figure out:

  1) whether the stock firmware is alive and listening
  2) what baud rate the firmware uses
  3) which commands it recognises (identity, protocol version, etc.)

Nothing here writes to flash or changes the device's state permanently.
The worst it can do is confuse a badly written serial parser for a moment.

Usage (Windows):
    py -m pip install pyserial          # once
    py tools\\probe_makcu.py COM3

Usage (Linux/macOS):
    python3 tools/probe_makcu.py /dev/ttyACM0
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import serial  # from pyserial
except ImportError:
    sys.exit(
        "pyserial is not installed. Run:\n"
        "    py -m pip install pyserial\n"
        "(or `python3 -m pip install pyserial` on Linux/macOS)"
    )


# Baud rates worth trying, most likely first.
#
# - 115200 is the plain-jane default for hobby firmware and the CH343's
#   power-on default.
# - 4_000_000 is what documented MAKCU firmware uses at "high speed" once
#   the host asks it to switch. The CH343 supports up to 6 Mbps.
# - 9600 is included because some very early / clone firmware defaults
#   there.
BAUD_RATES = [115200, 4_000_000, 921600, 500000, 250000, 9600]

# Commands to probe with. Each entry is (name, bytes_to_send).
#
# We try both `km.version` and `km.version()` because different community
# clients disagree on whether parentheses are required for zero-arg
# commands.
PROBES: list[tuple[str, bytes]] = [
    ("km.version",   b"km.version\r\n"),
    ("km.version()", b"km.version()\r\n"),
    ("km.hw",        b"km.hw\r\n"),
    ("version",      b"version\r\n"),
    ("?",            b"?\r\n"),
    ("AT",           b"AT\r\n"),  # in case it's an AT-command style chip
]

# How long to wait after sending each probe before reading a reply.
READ_TIMEOUT_S = 0.5


def dump(reply: bytes) -> str:
    """Show a serial reply in both a printable form and a hex dump.

    Some firmware sends binary framing or unusual line endings, so plain
    printing can hide what's actually on the wire.
    """
    printable = reply.decode("utf-8", errors="replace").replace("\r", "\\r").replace("\n", "\\n")
    hexdump = reply.hex(" ")
    return f"text={printable!r}  hex={hexdump}"


def probe(port: str, baud: int) -> bool:
    """Return True if the device replied to anything at this baud rate."""
    print(f"\n--- {baud:>7} baud ------------------------------------------")
    try:
        ser = serial.Serial(port, baud, timeout=READ_TIMEOUT_S)
    except serial.SerialException as e:
        print(f"  open failed: {e}")
        return False

    got_any = False
    with ser:
        # Drain anything the firmware may have blurted out on connect.
        time.sleep(0.1)
        stale = ser.read(4096)
        if stale:
            print(f"  banner: {dump(stale)}")
            got_any = True

        for name, payload in PROBES:
            ser.reset_input_buffer()
            ser.write(payload)
            ser.flush()
            time.sleep(READ_TIMEOUT_S)
            reply = ser.read(4096)
            marker = "OK  " if reply else "--  "
            print(f"  {marker}{name:<14}  ->  {dump(reply) if reply else '(silence)'}")
            if reply:
                got_any = True

    return got_any


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("port", help="Serial port, e.g. COM3 or /dev/ttyACM0")
    ap.add_argument(
        "--only",
        type=int,
        default=None,
        help="Only probe this one baud rate (skip the sweep).",
    )
    args = ap.parse_args()

    rates = [args.only] if args.only else BAUD_RATES

    any_response = False
    for baud in rates:
        if probe(args.port, baud):
            any_response = True

    print()
    if any_response:
        print("At least one baud rate got a response. Look for the baud where")
        print("the replies look like actual command output rather than garbled")
        print("bytes; that's the firmware's real baud rate.")
    else:
        print("Total silence at every baud rate tried. That means one of:")
        print("  - the firmware ignores unknown commands and doesn't echo")
        print("  - the firmware uses a binary framing we didn't send")
        print("  - the UART TX/RX lines aren't actually connected to the")
        print("    MCU we can talk to from this USB port")
        print("Next step: open a plain serial terminal, move the mouse, and")
        print("watch whether the port prints anything on its own.")
    return 0 if any_response else 1


if __name__ == "__main__":
    raise SystemExit(main())
