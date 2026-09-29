"""Interactive shell for the MAKCU stock firmware.

Opens the serial port at 115200 baud (confirmed working on the user's
hardware) and lets you type commands. Whatever the firmware sends back
prints in real time. `>>> ` is the firmware's own prompt.

Type `.help`   for local commands (script-side, not sent to device).
Type `.quit`   to exit.
Type `km.<name>` and press Enter to send a real MAKCU command.

Usage (Windows):
    py tools\\makcu_shell.py COM3

Usage (Linux/macOS):
    python3 tools/makcu_shell.py /dev/ttyACM0
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial is not installed. Run: py -m pip install pyserial")


LOCAL_HELP = """
Local commands (never sent to device):
  .help              this text
  .quit              close port and exit
  .raw <hex bytes>   send raw bytes, e.g. `.raw 6b 6d 0d 0a`
  .lineend crlf|lf|cr|none  choose what gets appended to your typed line
                            (default: crlf)
  .baud <n>          reopen the port at a different baud rate

Try (real device commands):
  km.version
  km.version()
  km.serial()
  km.echo(0)          usually disables local echo
  km.echo(1)          usually re-enables it
  km.baud(4000000)    switch to 4 Mbps  (then .baud 4000000 here to follow)
  km.move(20, 0)      move mouse right 20 px
  km.left(1)          press left button
  km.left(0)          release
"""


class Session:
    def __init__(self, port: str, baud: int) -> None:
        self.port = port
        self.baud = baud
        self.ser: serial.Serial | None = None
        self.line_ending = b"\r\n"
        self.stop = threading.Event()

    def open(self) -> None:
        self.ser = serial.Serial(self.port, self.baud, timeout=0.05)
        print(f"[opened {self.port} @ {self.baud} baud]", flush=True)

    def close(self) -> None:
        self.stop.set()
        if self.ser and self.ser.is_open:
            self.ser.close()

    def reader_loop(self) -> None:
        assert self.ser is not None
        while not self.stop.is_set():
            try:
                data = self.ser.read(256)
            except serial.SerialException:
                return
            if data:
                # Print exactly what came in, without newline translation, so
                # what you see is what the wire carried.
                sys.stdout.write(data.decode("utf-8", errors="replace"))
                sys.stdout.flush()

    def send(self, line: str) -> None:
        assert self.ser is not None
        payload = line.encode("utf-8") + self.line_ending
        self.ser.write(payload)
        self.ser.flush()


def handle_local(session: Session, cmd: str) -> bool:
    """Return True if the command was handled locally; False if it should
    be sent to the device."""
    if not cmd.startswith("."):
        return False

    parts = cmd.split()
    op = parts[0]

    if op == ".help":
        print(LOCAL_HELP)
    elif op == ".quit":
        session.close()
        raise SystemExit(0)
    elif op == ".raw":
        try:
            data = bytes.fromhex("".join(parts[1:]))
        except ValueError:
            print("[bad hex]")
            return True
        assert session.ser is not None
        session.ser.write(data)
        session.ser.flush()
        print(f"[sent {len(data)} bytes]")
    elif op == ".lineend":
        if len(parts) != 2:
            print("[.lineend crlf|lf|cr|none]")
            return True
        m = {"crlf": b"\r\n", "lf": b"\n", "cr": b"\r", "none": b""}
        if parts[1] not in m:
            print("[.lineend crlf|lf|cr|none]")
            return True
        session.line_ending = m[parts[1]]
        print(f"[line ending -> {parts[1]}]")
    elif op == ".baud":
        if len(parts) != 2 or not parts[1].isdigit():
            print("[.baud <int>]")
            return True
        new = int(parts[1])
        session.stop.set()
        assert session.ser is not None
        session.ser.close()
        time.sleep(0.1)
        session.stop.clear()
        session.baud = new
        session.open()
        threading.Thread(target=session.reader_loop, daemon=True).start()
    else:
        print(f"[unknown local command: {op} — try .help]")

    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("port", help="Serial port, e.g. COM3 or /dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    session = Session(args.port, args.baud)
    session.open()

    reader = threading.Thread(target=session.reader_loop, daemon=True)
    reader.start()

    print("[type .help for local commands, .quit to exit]")
    try:
        while True:
            try:
                line = input()
            except EOFError:
                break
            if not line:
                # Blank enter — still send it, some firmwares reprompt.
                session.send("")
                continue
            if handle_local(session, line):
                continue
            session.send(line)
    except KeyboardInterrupt:
        pass
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
