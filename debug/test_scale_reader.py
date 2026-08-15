"""Tests for scale_reader.py"""
from src.scale_reader import MockScale, HIDScale, normalize_to_kg, get_scale


def test_clean_read():
    """Mock scale returns deterministic value."""
    scale = MockScale(fixed_reading=2.5)
    qty, unit = scale.read()
    assert qty == 2.5
    assert unit == "kg"


def test_unit_conversion_grams_to_kg():
    """500g should normalize to 0.5kg."""
    assert normalize_to_kg(500, "g") == 0.5


def test_hidscale_read_returns_tuple():
    """HIDScale.read() must return (float, str), same shape as
    MockScale.read()."""
    scale = HIDScale("/dev/fake")
    scale._read_raw_report = lambda: (500.0, "g")
    scale._connect = lambda: setattr(scale, "_device", object())

    result = scale.read()
    assert isinstance(result, tuple)
    assert len(result) == 2
    qty, unit = result
    assert qty == 0.5
    assert unit == "kg"


def test_connect_failure_then_recovers():
    """If the initial connect() fails, read() should retry the
    connect itself and succeed once it comes back."""
    scale = HIDScale("/dev/fake")
    scale._retry_backoff_seconds = 0

    call_count = {"n": 0}

    def flaky_connect():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise OSError("simulated connect failure")
        scale._device = object()

    scale._connect = flaky_connect
    scale._read_raw_report = lambda: (1000.0, "g")

    qty, unit = scale.read()
    assert qty == 1.0
    assert unit == "kg"
    assert call_count["n"] == 3


def test_mid_read_disconnect_then_recovers():
    """A DIFFERENT scenario from connect failure: the device connects
    successfully, but _read_raw_report() itself fails (a genuine
    mid-read disconnect). read() should discard the stale device,
    reconnect, and succeed on retry."""
    scale = HIDScale("/dev/fake")
    scale._retry_backoff_seconds = 0

    class FakeDevice:
        def close(self):
            pass

    connect_calls = {"n": 0}
    read_calls = {"n": 0}

    def connect_ok():
        connect_calls["n"] += 1
        scale._device = FakeDevice()

    def read_fails_once_then_succeeds():
        read_calls["n"] += 1
        if read_calls["n"] == 1:
            raise OSError("simulated mid-read disconnect")
        return (750.0, "g")

    scale._connect = connect_ok
    scale._read_raw_report = read_fails_once_then_succeeds

    qty, unit = scale.read()
    assert qty == 0.75
    assert unit == "kg"
    assert connect_calls["n"] == 2, f"expected 2 connects, got {connect_calls['n']}"
    assert read_calls["n"] == 2


def test_device_closed_on_disconnect():
    """When a disconnect is caught, the stale device object should
    have close() called on it before being discarded."""
    scale = HIDScale("/dev/fake")
    scale._retry_backoff_seconds = 0

    close_calls = {"n": 0}

    class FakeDevice:
        def close(self):
            close_calls["n"] += 1

    scale._device = FakeDevice()

    attempt = {"n": 0}

    def connect_again():
        scale._device = object()

    def read_fails_once():
        attempt["n"] += 1
        if attempt["n"] == 1:
            raise OSError("disconnect")
        return (500.0, "g")

    scale._connect = connect_again
    scale._read_raw_report = read_fails_once

    scale.read()
    assert close_calls["n"] == 1


def test_disconnect_exceeds_retries_raises():
    """If the device never recovers, read() should raise RuntimeError
    after max_retries."""
    scale = HIDScale("/dev/fake")
    scale._retry_backoff_seconds = 0
    scale._connect = lambda: (_ for _ in ()).throw(OSError("permanently gone"))

    try:
        scale.read()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "did not recover" in str(e)


def test_unsupported_unit_rejected():
    """Pounds should raise ValueError."""
    try:
        normalize_to_kg(5, "lb")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_get_scale_defaults_to_mock():
    """With empty allowlist, factory returns MockScale."""
    assert isinstance(get_scale(), MockScale)

