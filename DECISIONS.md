# Decisions locked Day 1

## Currency schema

All monetary values stored as integer cents (`price_cents INTEGER`), never floats.

Quantities stay REAL to support fractional units (0.5 kg, 1.25 L).

## Scale hardware interface

HID device identified by vendor:product ID allowlist in `scale_reader.py`.

Default mode: interactive HID, evdev grab.

## Barcode scanner

Webcam only, OpenCV capture + pyzbar decode. No dedicated barcode-scanner hardware in v1.
