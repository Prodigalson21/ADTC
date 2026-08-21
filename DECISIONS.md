# Decisions locked Day 1

## Currency schema

All monetary values stored as integer cents (`price_cents INTEGER`), never floats.

Quantities stay REAL to support fractional units (0.5 kg, 1.25 L).

## Scale hardware interface

HID device identified by vendor:product ID allowlist in `scale_reader.py`.

Default mode: interactive HID, evdev grab.

## Barcode scanner

Webcam only, OpenCV capture + pyzbar decode. No dedicated barcode-scanner hardware in v1.

## llama-cpp-python compile flags
Locked: CMAKE_ARGS="-DGGML_AVX2=on -DGGML_CPU_REPACK=OFF"
Rationale: measured on dev hardware (WSL2), 2-3 runs each config.
RAM: repack-off measured 2165 MB vs repack-on 3433 MB -- large,
consistent, reliable difference (~1.27 GB saved).
Speed: repack-off ~9.32s avg vs repack-on ~9.54s avg (excluding
cold-start outliers) -- within noise, no reliable difference given
sample size. Repack-off wins on RAM with no measurable speed cost.
Re-verify on Day 8's actual audit hardware -- WSL2 is not the target
environment.
