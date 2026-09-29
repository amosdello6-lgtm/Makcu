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
