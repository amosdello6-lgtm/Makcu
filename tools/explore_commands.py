"""Sweep a batch of likely MAKCU commands and print each reply.

Non-destructive by default: does not press buttons, does not move the
mouse, does not change baud rate. The point is to map the command surface
of the stock firmware — which names exist, which spellings work, what
reply format is used — before writing the host library.

Usage:
    py tools\\explore_commands.py COM3
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial is not installed. Run: py -m pip install pyserial")


# Commands to try. Grouped by intent so the transcript is easy to read.
GROUPS: list[tuple[str, list[str]]] = [
    ("identity", [
        "km.version",
        "km.version()",
        "km.name",
        "km.name()",
        "km.serial",
        "km.serial()",
        "km.hw",
        "km.hw()",
        "km.chip",
        "km.chip()",
        "km.uid",
        "km.uid()",
        "km.info",
        "km.info()",
        "km.help",
        "km.help()",
        "help",
    ]),
    ("state (read only)", [
        "km.buttons",
        "km.buttons()",
        "km.mouse",
        "km.mouse()",
        "km.status",
        "km.status()",
        "km.locks",
        "km.locks()",
    ]),
    ("echo / prompt", [
        "km.echo",
        "km.echo()",
    ]),
    ("small nudges (may move mouse 1px)", [
        "km.move(0, 0)",
        "km.move(1, 0)",
        "km.wheel(0)",
    ]),
]


PROMPT_TAIL = b">>> "
READ_WINDOW_S = 0.6


def read_until_prompt(ser: serial.Serial, timeout_s: float = READ_WINDOW_S) -> bytes:
    """Read from the port until we see the `>>> ` prompt, or timeout."""
    deadline = time.time() + timeout_s
    buf = bytearray()
    while time.time() < deadline:
        chunk = ser.read(256)
        if chunk:
            buf.extend(chunk)
            if buf.endswith(PROMPT_TAIL):
                break
        else:
            # Short idle nap so we don't spin.
            time.sleep(0.02)
    return bytes(buf)


def fmt(reply: bytes) -> str:
    if not reply:
        return "(silence)"
    text = reply.decode("utf-8", errors="replace").replace("\r", "\\r").replace("\n", "\\n")
    return f"text={text!r}  hex={reply.hex(' ')}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("port")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    print(f"[opening {args.port} @ {args.baud}]")
    with serial.Serial(args.port, args.baud, timeout=0.05) as ser:
        # Drain anything already in the buffer.
        time.sleep(0.2)
        stale = ser.read(4096)
        if stale:
            print(f"[banner] {fmt(stale)}")

        for group_name, cmds in GROUPS:
            print(f"\n=== {group_name} ===")
            for cmd in cmds:
                ser.reset_input_buffer()
                ser.write(cmd.encode() + b"\r\n")
                ser.flush()
                reply = read_until_prompt(ser)
                # Strip the trailing prompt for readability.
                shown = reply[: -len(PROMPT_TAIL)] if reply.endswith(PROMPT_TAIL) else reply
                marker = "OK" if reply else "--"
                print(f"  [{marker}] {cmd:<24}  ->  {fmt(shown)}")

    print("\nDone. Look for: which names produced text, which returned nothing,")
    print("and whether any reply mentions a version string, serial number, or")
    print("chip family. That gives us the identity of the MCU behind the CH343.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
