# 01 — Architecture

The goal of this doc is to give you a mental model you can hold in your
head while reading the code. Every design choice below is made in service
of one thing: **the PC must see a single, well-behaved HID mouse whose
input is the sum of the real mouse plus commands from a host program.**

## The three concurrent workloads

The firmware is really three loops that share one piece of state:

```
┌──────────────────────────┐        ┌──────────────────────────┐
│  usb_host_task           │        │  cmd_parser_task         │
│  ───────────────         │        │  ───────────────         │
│  Poll real mouse.        │        │  Read CDC serial bytes.  │
│  Parse HID report.       │        │  Parse km.* commands.    │
│  Push (dx, dy, buttons,  │        │  Push injections into    │
│  wheel) into mixer.      │        │  mixer.                  │
└──────────────┬───────────┘        └──────────────┬───────────┘
               │                                   │
               ▼                                   ▼
              ┌──────────────────────────────────────┐
              │   mixer (shared state, mutex)         │
              │   ──────────────────────────         │
              │   Accumulate dx, dy, wheel.          │
              │   OR button bits.                    │
              │   Rate-limit → emit HID report.      │
              └──────────────┬───────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────────────┐
              │   usb_device_task                     │
              │   ──────────────────────────         │
              │   Send HID mouse report to PC        │
              │   at 1 kHz (or matched to real       │
              │   device's polling rate).             │
              └──────────────────────────────────────┘
```

Concurrency is unavoidable here — the real mouse might send a report while
the host program is mid-command, and the PC expects reports at a stable
polling rate regardless of what either input is doing. FreeRTOS tasks +
one mutex around the mixer state is enough; queues work too and are often
cleaner.

## Why USB Host is the hard part

Two things make USB Host non-trivial:

1. **You don't know what mouse will be plugged in.** Boot mice have a
   fixed 3-byte report format (`buttons, dx, dy`). Modern gaming mice send
   larger reports with 16-bit deltas, 8+ buttons, high-resolution wheels,
   sometimes even multi-report protocols. You have to fetch and *parse*
   the HID Report Descriptor to know where each field lives.
2. **You are the host.** You supply bus power, negotiate the device
   descriptor, set the configuration, and open the interrupt IN endpoint.
   The ESP-IDF USB Host stack handles the transport, but *you* write the
   HID class driver on top.

For v0 we take a shortcut: force **boot protocol** on the mouse
(`SET_PROTOCOL(0)`). Almost every mouse supports this, and the report
format is fixed. In v3 we swap that out for a real HID descriptor parser.

## Why USB Device is easier

We control the descriptors, so we get to describe a very simple device:

- **Interface 0**: HID mouse, boot protocol compatible, one interrupt IN
  endpoint, 8-byte reports.
- **Interface 1**: CDC ACM (virtual serial port), two bulk endpoints and
  one interrupt IN for line-state notifications.

TinyUSB (bundled with ESP-IDF) handles both classes; we just supply the
descriptors and callbacks.

The tricky bit is composite descriptors — the *combined* configuration
descriptor has to list the IAD (Interface Association Descriptor) that
groups the two CDC interfaces, then the HID interface. Get the order or
lengths wrong and Windows enumerates a "USB device not recognized". We'll
walk through the descriptor byte-by-byte when we build it.

## The mixer

The mixer is the smallest interesting piece of code in the project.

State (protected by a mutex):

```c
struct {
    int32_t  dx_accum;
    int32_t  dy_accum;
    int8_t   wheel_accum;
    uint8_t  buttons;              // last known state
    uint8_t  injected_buttons;     // OR'd in from commands
    bool     locked_x, locked_y;   // km.lock_x() etc.
    bool     locked_left, locked_right, ...;
} mixer;
```

Producers (USB host, command parser) call `mixer_add_delta()` and
`mixer_set_buttons()`. The device task calls `mixer_take_report()` on its
polling tick, which snapshots-and-clears the accumulators, applies the
lock mask, clamps to int8 (or int16 in high-res mode), and returns a
report ready to shove down the interrupt IN endpoint.

Two subtleties worth calling out early:

- **Rate mismatch.** If the real mouse polls at 1000 Hz and the PC-side
  device is also 1 kHz, most reports pass through 1:1. But when the host
  injects `km.move(500, 0)` in a single command, we can't emit a report
  with `dx=500` (int8 max is 127). We either split it across ticks or
  switch the descriptor to 16-bit deltas.
- **Button ownership.** A button click from the host must eventually
  produce a matching release. The parser has to track pending press/release
  pairs, otherwise the PC sees "stuck" buttons.

## Command protocol at a glance

Full spec in [`03-protocol.md`](03-protocol.md). One-liner: ASCII commands
terminated by `\n`, requests prefixed `km.`, replies mirror the request
name with a value. Example:

```
> km.move(120, -30)
< km.move:ok
> km.version
< km.version:0.1.0
```

Binary framing is a possible v2 upgrade; ASCII is fine for learning.

## What we're deliberately *not* doing

- **No USB descriptor cloning of a real mouse.** MAKCU-style products
  advertise a "serial spoofing" feature that makes the composite device
  present the real mouse's VID/PID to the OS. That exists to defeat
  anti-cheat. We use a distinct VID/PID that says "this is a hobby
  device", and the README calls it out.
- **No timing jitter models designed to look human.** Same reason.
- **No hidden features.** Every command in the parser is documented in
  `03-protocol.md`.

## Next reading

- [`02-usb-hid-primer.md`](02-usb-hid-primer.md) — enough USB HID to read
  the code without getting lost.
- [`03-protocol.md`](03-protocol.md) — the serial command surface.
- [`04-flashing-and-recovery.md`](04-flashing-and-recovery.md) — how to
  put custom code on your board without bricking it.
