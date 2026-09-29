"""High-level client for the MAKCU stock firmware.

Each method here corresponds to one command on the wire. Reply parsing
is intentionally hand-rolled per method (instead of a generic parser)
because the stock firmware's reply shapes are inconsistent — a separate
per-command parser is much easier to read than one that tries to be
clever about all cases.
"""

from __future__ import annotations

from typing import Optional

from .transport import Transport, DEFAULT_BAUD


class MakcuError(Exception):
    """Base class for anything the client raises."""


class NoMouseAttached(MakcuError):
    """A command that needs the passthrough mouse was rejected."""


class Makcu:
    """High-level MAKCU client.

    Usage:

        with Makcu("COM3") as mkc:
            print(mkc.name())
            mkc.click_left()

    You can also use it without the context manager, in which case you
    should call `close()` yourself.
    """

    def __init__(self, port: str, baud: int = DEFAULT_BAUD) -> None:
        self._tx = Transport(port, baud=baud)

    # ------------------------------------------------------------------
    # Lifetime
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._tx.close()

    def __enter__(self) -> "Makcu":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Identity / state
    # ------------------------------------------------------------------

    def name(self) -> str:
        """Return the device's self-identifier.

        On stock 3.2.0 this is `km.MAKCU`; we strip the `km.` prefix and
        return just `MAKCU`.
        """
        reply = self._tx.send_text("km.version()")
        return reply.removeprefix("km.").strip()

    def firmware_banner(self) -> str:
        """The 3.2.0 firmware only reveals its full version string in the
        boot banner, not in reply to any known command. This helper reads
        whatever is currently in the buffer, so if the caller has just
        triggered a reboot they can capture the banner. Otherwise returns
        an empty string."""
        return self._tx.send_raw("").decode("utf-8", errors="replace")

    def buttons(self) -> int:
        """Return the current mouse button mask.

        The bit layout matches the HID boot mouse convention on stock
        firmware: bit 0 = left, bit 1 = right, bit 2 = middle, etc.
        Returns 0 when no buttons are held (which is also what you get
        when no mouse is attached).
        """
        reply = self._tx.send_text("km.buttons()")
        try:
            return int(reply)
        except ValueError as e:
            raise MakcuError(f"km.buttons() returned unparseable {reply!r}") from e

    def mouse_serial(self) -> Optional[str]:
        """Return the USB serial number of the attached mouse, or None if
        the mouse has no serial (or no mouse is attached)."""
        reply = self._tx.send_text("km.serial()")
        # Reply examples:
        #   "km.Mouse does not have a serial number"  — no serial
        #   "km.<serial>"                              — probably (untested)
        payload = reply.removeprefix("km.").strip()
        if "does not have a serial number" in payload:
            return None
        return payload or None

    # ------------------------------------------------------------------
    # Mouse motion / buttons (WARNING: these need a mouse attached on
    # stock firmware v3.2.0 or the device will crash-reboot. We catch
    # the reboot after the fact but the reset is real.)
    # ------------------------------------------------------------------

    def move(self, dx: int, dy: int) -> None:
        """Move the mouse relatively by (dx, dy).

        Raises NoMouseAttached if we detect the crash-and-reboot signature
        that stock 3.2.0 emits when no passthrough mouse is present. Note
        that by the time we raise, the device has ALREADY rebooted.
        """
        reply = self._tx.send_raw(f"km.move({dx}, {dy})")
        text = reply.decode("utf-8", errors="replace")
        if "MAKCU" in text and "firmware version" in text:
            raise NoMouseAttached(
                "km.move triggered a crash-reboot. On stock v3.2.0 this "
                "means no passthrough mouse is attached. Plug a real "
                "mouse into the MAKCU's other USB port and try again."
            )

    def wheel(self, delta: int) -> None:
        """Rotate the wheel by `delta` detents (positive up, negative down)."""
        self._tx.send_raw(f"km.wheel({delta})")

    # -- button press/release helpers ---------------------------------

    def _set_button(self, name: str, pressed: bool) -> None:
        self._tx.send_raw(f"km.{name}({1 if pressed else 0})")

    def press_left(self) -> None:  self._set_button("left", True)
    def release_left(self) -> None: self._set_button("left", False)
    def press_right(self) -> None:  self._set_button("right", True)
    def release_right(self) -> None: self._set_button("right", False)
    def press_middle(self) -> None: self._set_button("middle", True)
    def release_middle(self) -> None: self._set_button("middle", False)

    def click_left(self, hold_ms: int = 30) -> None:
        """Press left, wait, release. `hold_ms` is host-side timing."""
        import time
        self.press_left()
        time.sleep(hold_ms / 1000.0)
        self.release_left()

    # ------------------------------------------------------------------
    # Escape hatch
    # ------------------------------------------------------------------

    def raw(self, command: str) -> str:
        """Send an arbitrary command and get the reply text. Useful for
        experimenting with commands we haven't wrapped yet."""
        return self._tx.send_text(command)
