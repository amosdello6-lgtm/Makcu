# Makcu — Custom Firmware (Learning Project)

A from-scratch reimplementation of MAKCU-style firmware, built to **learn how
these devices actually work** rather than to ship a product. Every piece is
written to be read: USB host + device stacks, HID descriptors, the serial
command protocol, and a matching Python host library.

> **Scope note.** This project stops at the firmware and protocol layer.
> It does not include game-cheating logic, recoil scripts, aim assist, or
> anti-detection features. If that's what you're after, this is the wrong
> repo.

## What a MAKCU is

A small board (mainstream units are **ESP32-S3** based) that sits on the USB
cable between a real mouse and a PC. To the PC it looks like a normal HID
mouse. Internally it forwards reports from the real mouse *and* mixes in
extra input coming from a host application over a second USB serial port.

```
                             ┌──────────── firmware ─────────────┐
[Real Mouse] ── USB ─────►   │  USB Host  →  Mixer  →  USB Device│  ── USB ──► [PC]
                             │                   ▲               │
                             │                   │               │
                             │           CDC serial parser       │
                             └───────────────────┬───────────────┘
                                                 │
                                        [PC host app: km.move(), etc.]
```

Three interesting things run at the same time:

1. **USB Host** — reads HID reports from the real mouse.
2. **USB Device** — presents itself to the PC as a HID mouse (plus a CDC
   serial endpoint for the command channel).
3. **Mixer / parser** — merges live mouse reports with injected commands
   into the outgoing HID stream.

Read [`docs/01-architecture.md`](docs/01-architecture.md) for the long
version.

## Repository layout

```
Makcu/
├── README.md              ← you are here
├── docs/                  ← the learning material
│   ├── 01-architecture.md
│   ├── 02-usb-hid-primer.md
│   ├── 03-protocol.md
│   └── 04-flashing-and-recovery.md
├── firmware/              ← ESP-IDF firmware (added in next step)
│   └── main/
└── host/                  ← Python client library (added in next step)
    └── makcu_host/
```

## Roadmap

- [x] Repo skeleton + architecture docs
- [ ] **Back up the stock firmware** on your MAKCU before flashing anything
      custom (see [`docs/04-flashing-and-recovery.md`](docs/04-flashing-and-recovery.md))
- [ ] Enumerate the target hardware (chip, flash size, USB pins)
- [ ] Firmware v0: composite USB device (HID mouse + CDC serial), no host
      yet — PC sees a fake mouse it can command via the serial port
- [ ] Host v0: minimal Python client (`Makcu.move`, `Makcu.click`) talking
      to firmware v0
- [ ] Firmware v1: add USB Host, read real mouse, pass reports through
- [ ] Firmware v2: mixer — merge real reports + injected commands
- [ ] Firmware v3: full command set (buttons, wheel, absolute + relative
      moves, lock/unlock, serial spoofing off — that last one intentionally)

Each step lands with a doc explaining what it teaches and why the code is
written that way.

## Before you flash anything

**Read [`docs/04-flashing-and-recovery.md`](docs/04-flashing-and-recovery.md)
first.** A bad flash is recoverable on ESP32-S3 (BOOT + RESET drops it into
the ROM bootloader) but only if you know the pinout for your specific
board. Back up the stock firmware image before overwriting it.
