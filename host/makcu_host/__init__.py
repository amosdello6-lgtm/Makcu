"""makcu_host — a small, readable client for MAKCU-style serial firmware.

The design goal is clarity over cleverness: every method maps to exactly
one wire-level command, the parsing is line-oriented and easy to follow,
and there is one public class you construct with a serial port name.

Example:
    from makcu_host import Makcu
    with Makcu("COM3") as mkc:
        print(mkc.name())
        mkc.click_left()
"""

from .client import Makcu, MakcuError, NoMouseAttached

__all__ = ["Makcu", "MakcuError", "NoMouseAttached"]
