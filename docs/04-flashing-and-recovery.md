# 04 — Flashing and Recovery (READ BEFORE YOU FLASH)

Real hardware, real risk. This doc is the one you re-read every time
before pressing "flash". Even a "bricked" ESP32-S3 is almost always
recoverable — but only if you know the two escape hatches: **the ROM
bootloader** and **the backup image you took before you started**.

## Before you touch the flash tool

### 1. Identify the chip and board

Plug the MAKCU in and, before flashing anything, get:

```bash
# Linux / macOS
python -m esptool --port /dev/ttyACM0 chip_id
python -m esptool --port /dev/ttyACM0 flash_id
```

You want to know:

- **Chip name** — almost certainly `ESP32-S3`. If it says `CH552` or
  `CH32V` you have an older/clone unit and this document doesn't fully
  apply — the workflow is different (WCHISPTool, not esptool). Stop and
  tell me which chip you have.
- **Flash size** — usually 4 MB or 8 MB. Determines the partition table.
- **Crystal frequency** — 40 MHz on ESP32-S3.

`esptool` finds the port on its own if you omit `--port`, but explicit
is better.

### 2. Back up the stock firmware

This is not optional.

```bash
# Read the full flash out to a file. Size = your flash chip's size.
python -m esptool --port /dev/ttyACM0 --baud 460800 read_flash 0 0x400000 stock-firmware.bin
```

Keep `stock-firmware.bin` somewhere safe. If anything goes wrong you
restore it with:

```bash
python -m esptool --port /dev/ttyACM0 --baud 460800 write_flash 0 stock-firmware.bin
```

### 3. Know how to enter the ROM bootloader manually

Even if your own firmware crashes on boot, the ESP32-S3's *ROM* bootloader
is on-chip and cannot be erased. To enter it manually:

1. Hold **BOOT** (also labeled IO0 or GPIO0 on some boards).
2. Tap **RESET** (or unplug/replug the USB).
3. Release BOOT.

The device now enumerates as a plain USB serial device in download mode.
esptool will find it. This is your safety net. Every time you flash
custom code, know which physical buttons on your specific MAKCU do this
— take a photo of the board if the labels are tiny.

If the BOOT button isn't exposed on the case, you can usually short two
pads on the PCB briefly to ground on power-up. **Don't do this until
you've searched for a schematic for your exact MAKCU revision.**

## Flashing our firmware (once we have it)

The `firmware/` project will be an ESP-IDF app. The build produces three
binaries plus a partition table:

- `bootloader.bin` at `0x0`
- `partition-table.bin` at `0x8000`
- `makcu-firmware.bin` at `0x10000`

Flash with:

```bash
cd firmware
idf.py -p /dev/ttyACM0 flash monitor
```

`idf.py flash` handles the offsets automatically. `monitor` opens a
serial monitor with symbolic backtraces — invaluable when it crashes.

Ctrl+] exits the monitor without rebooting the device.

## Failure modes and what to do

### "Failed to connect: Timed out waiting for packet header"

esptool couldn't put the chip into download mode. Enter the bootloader
manually (BOOT+RESET as above) and try again. If it still fails:

- Wrong port? `ls /dev/tty*` before and after unplug to identify.
- USB cable is charge-only? Try a different cable. Real one.
- Some ESP32-S3 boards have two USB ports (USB-Serial via a bridge chip
  vs. native USB). Try the other one.

### The device boots our firmware but the PC doesn't see the mouse

Not bricked. The USB *device* stack is misbehaving but the ROM bootloader
still works. Fix the code, `idf.py flash` again.

### The device doesn't enumerate as anything after flashing

Enter the ROM bootloader manually (BOOT+RESET). It will *always* enumerate
in download mode. Restore the backup:

```bash
python -m esptool write_flash 0 stock-firmware.bin
```

Or, if you want to try again with new code, just re-flash the new build.

### Anti-brick reflex

If you're about to do something that *might* not boot — new partition
table, changed sdkconfig for USB — flash the bootloader and partition
table separately first and verify they boot, then flash the app. Failure
in the app leaves the bootloader intact and OTA-recoverable.

## Fuses: don't touch them

ESP32-S3 has one-time-programmable eFuses that control things like Secure
Boot, flash encryption, and the JTAG interface. Once burned, they cannot
be un-burned. **Don't run any `espefuse` command** on this device unless
you've read the ESP32-S3 eFuse Manager docs cover to cover and know
exactly what you're doing. There is no recovery from a mis-burned fuse.

## Legal / warranty note

Flashing custom firmware on the MAKCU obviously voids any warranty and
will replace whatever was there. That's the whole point. If the device
was rented, borrowed, or on someone else's payment card, ask them first.

## Checklist before every flash

- [ ] Backup image `stock-firmware.bin` exists and I know where
- [ ] I know which buttons on this specific board do BOOT+RESET
- [ ] The port name in my `idf.py -p` argument is right
- [ ] I'm flashing the right project (not last week's experiment)
- [ ] If touching partitions / bootloader: I've read the diff
