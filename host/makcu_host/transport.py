"""Low-level serial transport for MAKCU stock firmware.

Everything about the wire format is captured here so the client code
above it stays high-level.

What the stock firmware does (see docs/05-stock-firmware.md):

- Accepts commands terminated by `\r\n`.
- Emits replies with inconsistent line endings.
- Terminates each reply with the literal ASCII string `>>> ` (with a
  trailing space).
- Silently drops unknown commands.

We handle those quirks by reading bytes until we either see the prompt
tail or the read window expires, then returning the payload with the
prompt stripped and any leading command-echo line removed.
"""

from __future__ import annotations

import time

import serial


PROMPT = b">>> "
DEFAULT_BAUD = 115200


class Transport:
    def __init__(self, port: str, baud: int = DEFAULT_BAUD, timeout_s: float = 0.5) -> None:
        # timeout_s is the *per-read* timeout the underlying pyserial call
        # uses. Our reply reader loops on top of that up to `wait_s`.
        self._ser = serial.Serial(port, baud, timeout=0.05)
        self._wait_s = timeout_s
        # Give the firmware a moment after open to emit any banner it
        # would send on connect, then discard it so the first real reply
        # starts from a clean buffer.
        time.sleep(0.1)
        self._ser.reset_input_buffer()

    # ------------------------------------------------------------------
    # Lifetime
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Wire I/O
    # ------------------------------------------------------------------

    def send_raw(self, line: str) -> bytes:
        """Send `line` + CRLF and return the reply body (bytes).

        The returned bytes have the trailing `>>> ` prompt stripped, and
        the leading command echo (if any) stripped, but line endings are
        left as-is because the firmware isn't consistent about them.
        """
        self._ser.reset_input_buffer()
        self._ser.write(line.encode("utf-8") + b"\r\n")
        self._ser.flush()

        buf = bytearray()
        deadline = time.time() + self._wait_s
        while time.time() < deadline:
            chunk = self._ser.read(256)
            if chunk:
                buf.extend(chunk)
                if buf.endswith(PROMPT):
                    break
            else:
                time.sleep(0.02)

        payload = bytes(buf)
        if payload.endswith(PROMPT):
            payload = payload[: -len(PROMPT)]

        # Some replies begin with an echo of the command we sent, e.g.
        # `km.buttons()\n0\r\n`. Strip a matching prefix + first LF or CRLF
        # if we find it.
        echo = line.encode("utf-8")
        if payload.startswith(echo):
            after = payload[len(echo):]
            if after.startswith(b"\r\n"):
                payload = after[2:]
            elif after.startswith(b"\n"):
                payload = after[1:]

        return payload

    def send_text(self, line: str) -> str:
        """Convenience: send a command and return the reply as a stripped
        UTF-8 string, with any trailing whitespace/newlines removed."""
        return self.send_raw(line).decode("utf-8", errors="replace").strip()
