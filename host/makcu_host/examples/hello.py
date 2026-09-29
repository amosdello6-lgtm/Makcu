"""Minimum viable interaction with the MAKCU stock firmware.

Reads identity + button state, then (if a mouse is attached) nudges the
cursor slightly to prove the injection path works.

Usage:
    py host\\makcu_host\\examples\\hello.py COM3
"""

from __future__ import annotations

import argparse
import sys

# Allow running the file directly from the repo without installing the
# package.
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from makcu_host import Makcu, NoMouseAttached  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("port", help="Serial port, e.g. COM3 or /dev/ttyACM0")
    args = ap.parse_args()

    with Makcu(args.port) as mkc:
        print(f"device name:   {mkc.name()!r}")
        print(f"buttons mask:  0x{mkc.buttons():02x}")
        mouse_serial = mkc.mouse_serial()
        print(f"mouse serial:  {mouse_serial!r}")

        print("\nAttempting km.move(3, 0)...")
        try:
            mkc.move(3, 0)
            print("  moved. If you see your cursor jump 3px right, injection works.")
        except NoMouseAttached as e:
            print(f"  {e}")
            print("  (This is expected if you don't have a mouse plugged into the")
            print("   MAKCU's passthrough port. Everything else worked.)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
