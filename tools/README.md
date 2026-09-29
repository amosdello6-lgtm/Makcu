# tools/

One-off scripts for poking at hardware, dumping firmware, and other things
that don't belong in the runtime code. Nothing here is imported by
`firmware/` or `host/`.

## `probe_makcu.py`

Sweeps common baud rates on the MAKCU's CH343 UART bridge and prints
whatever the stock firmware sends back to each of a few probe commands.
Use it to confirm the firmware is alive and figure out its baud rate
before writing any real client code.

```
py -m pip install pyserial
py tools\probe_makcu.py COM3
```

## `explore_commands.py`

Once the baud rate is known (115200 on the current unit), this sends a
bigger batch of candidate `km.*` commands and prints each reply, so we
can map the command surface without typing them one at a time. Waits for
the `>>> ` prompt as its per-command reply delimiter.

```
py tools\explore_commands.py COM3
```

## `makcu_shell.py`

Interactive REPL over the serial port. Whatever the firmware sends prints
live; whatever you type is sent on Enter (with `\r\n` by default). Local
commands start with `.`:

- `.help` — list local commands
- `.raw 6b 6d 0d 0a` — send raw hex bytes
- `.lineend crlf|lf|cr|none` — change what gets appended to your input
- `.baud 4000000` — reopen the port at a new baud
- `.quit` — exit

```
py tools\makcu_shell.py COM3
```
