"""
scale_reader.py -- USB HID digital scale interface.

Falls back to MockScale if no real, allowlisted scale is found -- lets
the rest of the system be built and tested before real hardware is
available.

Design / review fixes:
1. HIDScale.read() catches OSError for real evdev device I/O failures,
   including disconnects. It does not catch unrelated exceptions.
2. find_scale_device() closes every InputDevice it opens, including
   the matching device. HIDScale creates its own independent connection.
3. Raw HID reports are represented as (value, unit), so normalization
   does not assume that every future scale reports grams.
4. HIDScale.read() returns the same (float, str) interface as MockScale.
5. A stale HID device is explicitly closed after an OSError before the
   connection reference is discarded.
6. get_scale() gracefully falls back to MockScale for expected hardware
   discovery failures (OSError) and a missing evdev dependency
   (ImportError), while allowing unrelated programming errors to surface.
"""

import random
import time


# Vendor:Product ID allowlist for real scales.
#
# This is a hard security boundary, not a convenience list:
# only explicitly approved device IDs are ever treated as a trusted
# scale.
#
# Do NOT add a placeholder or guessed ID here. Leave this empty until
# the actual scale is physically connected and its real vendor:product
# ID has been identified with `lsusb`.
SCALE_ALLOWLIST = [
    # (0x0922, 0x8004),  # example only -- replace with actual scale ID
]


# Conversion functions into the canonical kg unit.
#
# Unsupported units must be rejected rather than silently guessed.
UNIT_CONVERSIONS = {
    ("g", "kg"): lambda value: value / 1000.0,
    ("kg", "kg"): lambda value: value,
}


def normalize_to_kg(quantity: float, unit: str) -> float:
    """Convert a raw reading into kg.

    Args:
        quantity: Numeric quantity reported by the scale.
        unit: Unit reported by the scale, e.g. "g" or "kg".

    Returns:
        The quantity converted to kilograms.

    Raises:
        ValueError: If the supplied unit is not explicitly supported.
    """
    unit = unit.lower().strip()
    key = (unit, "kg")

    if key not in UNIT_CONVERSIONS:
        raise ValueError(
            f"Unsupported unit for normalization: {unit}"
        )

    return UNIT_CONVERSIONS[key](quantity)


class MockScale:
    """Fake scale used when real hardware is unavailable.

    Pass fixed_reading for deterministic tests. If omitted, a random
    reading is generated for demos/manual testing.
    """

    def __init__(self, fixed_reading: float = None):
        self._fixed_reading = fixed_reading

    def read(self) -> tuple[float, str]:
        """Return a simulated reading as (quantity, unit)."""
        if self._fixed_reading is not None:
            return (self._fixed_reading, "kg")

        raw_grams = random.uniform(100, 5000)
        return (normalize_to_kg(raw_grams, "g"), "kg")


class HIDScale:
    """Real USB HID scale interface using evdev.

    This class should only be instantiated after
    find_scale_device() has identified a device whose vendor:product
    ID is present in SCALE_ALLOWLIST.
    """

    def __init__(self, device_path: str):
        import evdev

        self._evdev = evdev
        self.device_path = device_path
        self._device = None

        self._max_retries = 3
        self._retry_backoff_seconds = 1.0

    def _connect(self):
        """Open and grab the HID device."""
        self._device = self._evdev.InputDevice(self.device_path)
        self._device.grab()

    def read(self) -> tuple[float, str]:
        """Read one weight value.

        Retries when evdev reports an OSError, covering both:
        - failure during initial connection
        - disconnect during an existing read

        The stale device object is closed before retrying.

        Returns:
            (quantity_in_kg, "kg")

        Raises:
            RuntimeError: If the device does not recover after all
                configured retries.
            ValueError: If the raw report contains an unsupported unit.
            NotImplementedError: Until the real scale's HID report
                parser has been implemented.
        """
        last_error = None

        for attempt in range(self._max_retries):
            try:
                if self._device is None:
                    self._connect()

                raw_value, raw_unit = self._read_raw_report()

                # The public interface is identical to MockScale:
                # always return (quantity, unit).
                return (
                    normalize_to_kg(raw_value, raw_unit),
                    "kg",
                )

            except OSError as error:
                # OSError is the expected evdev I/O failure type for
                # conditions such as a device being disconnected.
                last_error = error

                if self._device is not None:
                    try:
                        self._device.close()
                    except OSError:
                        # The descriptor may already be invalid after
                        # the disconnect. There is nothing further to
                        # clean up here.
                        pass

                self._device = None

                time.sleep(
                    self._retry_backoff_seconds * (attempt + 1)
                )

        raise RuntimeError(
            "Scale disconnected and did not recover after "
            f"{self._max_retries} attempts: {last_error}"
        )

    def _read_raw_report(self) -> tuple[float, str]:
        """Read and parse one raw HID report.

        Returns:
            (raw_value, raw_unit)

        The exact report format is scale-model-specific. This method
        must be implemented against the actual scale once hardware is
        available.

        Use:

            python -m evdev.evtest

        to inspect the real device's event/report behavior before
        implementing the parser.

        Keeping the unit in this return value means read() does not
        need to change if the actual scale reports in grams, kilograms,
        or another explicitly supported native unit.
        """
        raise NotImplementedError(
            "Fill in real HID report parsing once actual scale "
            "hardware is available. Use MockScale until then."
        )


def find_scale_device():
    """Find the first connected allowlisted scale.

    Every InputDevice opened during discovery is closed before this
    function returns, including a matching device.

    HIDScale will establish its own independent connection after the
    matching path has been identified. This prevents discovery from
    leaking an open file descriptor or retaining a stale device handle.
    """
    import evdev

    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)

        try:
            ids = (dev.info.vendor, dev.info.product)

            if ids in SCALE_ALLOWLIST:
                return path

        finally:
            # Always release the discovery handle, whether this device
            # matched or an exception occurred while inspecting it.
            dev.close()

    return None


def get_scale():
    """Return the appropriate scale implementation.

    Returns:
        HIDScale: When an allowlisted physical scale is discovered.
        MockScale: When no allowlist is configured, no matching scale
            is connected, evdev is unavailable, or hardware discovery
            fails with OSError.

    Only expected hardware/dependency failures are converted into the
    mock fallback. Unrelated programming errors are deliberately allowed
    to surface instead of being silently hidden.
    """
    if not SCALE_ALLOWLIST:
        return MockScale()

    try:
        device_path = find_scale_device()

    except (OSError, ImportError):
        # OSError: expected hardware/discovery failure.
        # ImportError: evdev is unavailable, so real HID hardware
        # cannot be used. Both fit the project's graceful-degradation
        # design.
        return MockScale()

    if device_path:
        return HIDScale(device_path)

    return MockScale()


if __name__ == "__main__":
    print("=== scale_reader.py self-test ===")

    # ---------------------------------------------------------------
    # Unit conversion
    # ---------------------------------------------------------------

    assert normalize_to_kg(500, "g") == 0.5
    assert normalize_to_kg(1.0, "kg") == 1.0
    print("OK: unit conversion (500g -> 0.5kg)")

    # ---------------------------------------------------------------
    # Deterministic MockScale
    # ---------------------------------------------------------------

    scale = MockScale(fixed_reading=0.5)
    qty, unit = scale.read()

    assert qty == 0.5
    assert unit == "kg"

    print(
        f"OK: MockScale deterministic reading -> "
        f"{qty} {unit}"
    )

    # ---------------------------------------------------------------
    # Random MockScale
    # ---------------------------------------------------------------

    scale2 = MockScale()
    qty2, unit2 = scale2.read()

    assert 0 < qty2 < 10
    assert unit2 == "kg"

    print(
        f"OK: MockScale random reading (secondary check) -> "
        f"{qty2:.3f} {unit2}"
    )

    # ---------------------------------------------------------------
    # Factory fallback
    # ---------------------------------------------------------------

    default_scale = get_scale()

    assert isinstance(default_scale, MockScale)

    print(
        "OK: get_scale() defaults to MockScale "
        "with empty allowlist"
    )

    # ---------------------------------------------------------------
    # Unsupported-unit rejection
    # ---------------------------------------------------------------

    try:
        normalize_to_kg(5, "lb")
        print("BUG: unsupported unit was NOT rejected")

    except ValueError as error:
        print(
            "OK: unsupported unit rejected "
            f"(already worked, re-confirmed): {error}"
        )

    print("\nAll self-tests passed.")