# 02 — Enough USB HID to read the code

You don't need to become a USB expert to work on this firmware. You do
need to know these pieces well enough that when you see them in code,
you're not guessing.

## Descriptors, top down

A USB device tells the host who it is through a tree of descriptors.
Here's the tree for our composite device:

```
Device Descriptor          (who am I, what class, VID/PID)
└── Configuration Descriptor
    ├── IAD                (says "next 2 interfaces are one CDC function")
    ├── Interface 0        (CDC control)  ── Endpoint (notify)
    ├── Interface 1        (CDC data)     ── Endpoints (bulk IN, bulk OUT)
    └── Interface 2        (HID mouse)    ── Endpoint (interrupt IN)
        └── HID Descriptor points to → Report Descriptor
```

The host reads the device descriptor first, then the configuration
descriptor (which is one big blob containing everything below it), then
for HID interfaces it separately fetches the *report descriptor*.

### The Report Descriptor is where the magic is

The report descriptor doesn't describe the device — it describes the
*layout of bytes* the device will send. Think of it as a schema for the
HID reports.

Here's a minimal boot-mouse report descriptor with comments:

```
0x05, 0x01,        // Usage Page (Generic Desktop)
0x09, 0x02,        // Usage (Mouse)
0xA1, 0x01,        // Collection (Application)
0x09, 0x01,        //   Usage (Pointer)
0xA1, 0x00,        //   Collection (Physical)
0x05, 0x09,        //     Usage Page (Button)
0x19, 0x01,        //     Usage Minimum (1)
0x29, 0x03,        //     Usage Maximum (3)
0x15, 0x00,        //     Logical Minimum (0)
0x25, 0x01,        //     Logical Maximum (1)
0x95, 0x03,        //     Report Count (3)
0x75, 0x01,        //     Report Size (1 bit)
0x81, 0x02,        //     Input (Data, Var, Abs)  ← 3 button bits
0x95, 0x01,        //     Report Count (1)
0x75, 0x05,        //     Report Size (5 bits)
0x81, 0x03,        //     Input (Cnst, Var, Abs)  ← padding
0x05, 0x01,        //     Usage Page (Generic Desktop)
0x09, 0x30,        //     Usage (X)
0x09, 0x31,        //     Usage (Y)
0x15, 0x81,        //     Logical Minimum (-127)
0x25, 0x7F,        //     Logical Maximum (127)
0x75, 0x08,        //     Report Size (8 bits)
0x95, 0x02,        //     Report Count (2)
0x81, 0x06,        //     Input (Data, Var, Rel)  ← dx, dy
0xC0,              //   End Collection
0xC0               // End Collection
```

The report itself is then 3 bytes:

```
byte 0: bit0=L bit1=R bit2=M  (buttons, upper 5 bits padding)
byte 1: dx  (signed int8)
byte 2: dy  (signed int8)
```

Our real firmware will use a slightly bigger report (5 buttons, 16-bit
deltas, wheel) but the shape is the same.

## Boot protocol vs. Report protocol

Every HID mouse supports two modes:

- **Boot protocol** — fixed 3-byte report layout as above. Guaranteed to
  work with any host, including BIOSes.
- **Report protocol** — whatever the mouse's report descriptor says. This
  is where gaming mice put their extra buttons, high-DPI 16-bit deltas,
  side scrolls, etc.

Mice boot in Report mode. To force Boot mode we send a
`SET_PROTOCOL(0)` request on the control endpoint. This is the shortcut
we use in v0 so we don't have to parse the report descriptor of every
random mouse. For real HID passthrough (v3) we swap to Report mode and
parse the descriptor.

## Endpoint types you'll see

- **Control (EP0)** — every device has one. Used for enumeration
  (descriptor reads) and class requests (like SET_PROTOCOL).
- **Interrupt** — small, polled at a fixed interval (1 ms is typical for
  mice at 1000 Hz). What we use for HID reports in both directions.
- **Bulk** — large, "get to it when you can". Used by CDC for the actual
  serial data.

You will not need Isochronous endpoints for this project.

## Polling rate

The device declares a `bInterval` in its endpoint descriptor. For full-
speed USB devices (which our ESP32-S3 is by default), `bInterval` is the
number of milliseconds between polls, `1..255`. For a 1000 Hz mouse we
set `bInterval = 1`.

The host also has a say — it can poll less often than the device asked
for. Windows in particular has historically capped some mice at 125 Hz
until USB 3 came into the picture. Not our problem for the firmware, but
worth knowing when the host application's `km.move` looks laggy and it
turns out the OS is polling us at 8 ms intervals.

## Composite device gotcha: the IAD

CDC uses two interfaces (control + data) that must be grouped. On modern
Windows the OS will figure it out; on some setups you need an **Interface
Association Descriptor (IAD)** in the configuration descriptor to
explicitly say "the next 2 interfaces are one function". Skip it and you
get either "USB device not recognized" or Windows loading two separate
drivers on the two halves. TinyUSB emits the IAD automatically when you
use its composite templates; if we hand-roll descriptors we have to
remember it.

## Where this shows up in code

- `firmware/main/hid_descriptors.c` — the report descriptors, both for the
  device we present and (in v3) for parsing what the real mouse presents.
- `firmware/main/usb_device.c` — the device-side configuration and
  callbacks.
- `firmware/main/usb_host.c` — the host-side enumeration, SET_PROTOCOL
  request, and the polling loop.

## Recommended reading (external)

- **USB HID 1.11 spec** — dense but the definitive reference for report
  descriptor items.
- **usb.org "HID Usage Tables"** — the enum of every Usage Page / Usage
  code. You'll be looking things up in this constantly.
- **BeyondLogic USB in a NutShell** — friendlier intro if you've never
  touched USB before.

Don't try to read those cover-to-cover. Read them when you hit a specific
question in the code.
