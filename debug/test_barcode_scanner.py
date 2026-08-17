"""Tests for barcode_scanner.py (ChatGPT-thread implementation)."""
import time
from unittest.mock import MagicMock, patch

from src.barcode_scanner import BarcodeScanner


class MockDecoded:
    def __init__(self, data):
        self.data = data


def _make_mocks():
    mock_cv2 = MagicMock()
    mock_cap = MagicMock()
    mock_cv2.VideoCapture.return_value = mock_cap
    mock_pyzbar_pkg = MagicMock()
    mock_dec = mock_pyzbar_pkg.pyzbar
    return mock_cv2, mock_cap, mock_pyzbar_pkg, mock_dec


def test_missing_dependencies_degrade_gracefully():
    """No cv2/pyzbar installed -> start() returns False, doesn't crash."""
    with patch.dict("sys.modules", {"cv2": None, "pyzbar": None}):
        scanner = BarcodeScanner()
        assert scanner.start() is False
        assert scanner.available is False
        assert scanner.running is False
        assert "unavailable" in scanner.error.lower()


def test_webcam_unavailable_degrades_gracefully():
    """cv2 installed but no webcam -> start() returns False, doesn't crash."""
    mock_cv2, mock_cap, mock_pkg, mock_dec = _make_mocks()
    mock_cap.isOpened.return_value = False

    with patch.dict("sys.modules", {"cv2": mock_cv2, "pyzbar": mock_pkg}):
        scanner = BarcodeScanner()
        assert scanner.start() is False
        assert scanner.available is False
        assert scanner.error == "Webcam unavailable"
        assert mock_cap.release.called, "camera should be released when unopened"


def test_negative_debounce_rejected():
    """Constructor should reject a negative debounce window immediately."""
    try:
        BarcodeScanner(debounce_seconds=-1)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_clean_scan_and_get_latest():
    """A successfully decoded value should appear via get_latest()."""
    mock_cv2, mock_cap, mock_pkg, mock_dec = _make_mocks()
    mock_cap.isOpened.return_value = True
    frame = MagicMock()
    mock_cap.read.return_value = (True, frame)
    mock_dec.decode.return_value = [MockDecoded(b"CODE-A")]

    with patch.dict("sys.modules", {"cv2": mock_cv2, "pyzbar": mock_pkg}):
        scanner = BarcodeScanner()
        assert scanner.start() is True

        deadline = time.monotonic() + 2.0
        result = None
        while result is None and time.monotonic() < deadline:
            result = scanner.get_latest()
            if result is None:
                time.sleep(0.01)

        assert result == "CODE-A"
        scanner.stop()


def test_same_code_debounced():
    """The same code decoded repeatedly within the debounce window should
    not keep re-registering as new."""
    mock_cv2, mock_cap, mock_pkg, mock_dec = _make_mocks()
    mock_cap.isOpened.return_value = True
    frame = MagicMock()
    mock_cap.read.return_value = (True, frame)
    mock_dec.decode.return_value = [MockDecoded(b"CODE-A")]

    with patch.dict("sys.modules", {"cv2": mock_cv2, "pyzbar": mock_pkg}):
        scanner = BarcodeScanner(debounce_seconds=10.0)
        assert scanner.start() is True

        deadline = time.monotonic() + 2.0
        while scanner.get_latest() is None and time.monotonic() < deadline:
            time.sleep(0.01)

        scanner.get_latest(clear=True)
        time.sleep(0.2)
        assert scanner.get_latest() is None, "same code within debounce window should not re-register"
        scanner.stop()


def test_different_code_not_debounced():
    """A genuinely different code should register, using clear=True to
    consume CODE-A before waiting for CODE-B -- avoids the real race
    of checking a stale, unconsumed value."""
    mock_cv2, mock_cap, mock_pkg, mock_dec = _make_mocks()
    mock_cap.isOpened.return_value = True
    frame = MagicMock()
    mock_cap.read.return_value = (True, frame)
    mock_dec.decode.return_value = [MockDecoded(b"CODE-A")]

    with patch.dict("sys.modules", {"cv2": mock_cv2, "pyzbar": mock_pkg}):
        scanner = BarcodeScanner()
        scanner.start()

        deadline = time.monotonic() + 1.0
        while scanner.get_latest(clear=True) is None and time.monotonic() < deadline:
            time.sleep(0.01)

        mock_dec.decode.return_value = [MockDecoded(b"CODE-B")]

        deadline = time.monotonic() + 1.0
        result = None
        while result is None and time.monotonic() < deadline:
            result = scanner.get_latest(clear=True)
            if result is None:
                time.sleep(0.01)

        assert result == "CODE-B"
        scanner.stop()


def test_disconnect_mid_run_recovers():
    """Transient frame drops (graceful (False, None) returns) must not
    kill the scanner -- uses a callable side_effect that never runs out."""
    mock_cv2, mock_cap, mock_pkg, mock_dec = _make_mocks()
    mock_cap.isOpened.return_value = True
    frame = MagicMock()

    call_log = {"n": 0}

    def flaky_read():
        call_log["n"] += 1
        if call_log["n"] <= 3:
            return (False, None)
        return (True, frame)

    mock_cap.read.side_effect = flaky_read
    mock_dec.decode.return_value = [MockDecoded(b"RESILIENT")]

    with patch.dict("sys.modules", {"cv2": mock_cv2, "pyzbar": mock_pkg}):
        scanner = BarcodeScanner()
        assert scanner.start() is True

        deadline = time.monotonic() + 2.0
        result = None
        while result is None and time.monotonic() < deadline:
            result = scanner.get_latest()
            if result is None:
                time.sleep(0.01)

        assert result == "RESILIENT"
        assert scanner.running is True
        scanner.stop()


def test_runtime_exception_is_recorded_and_logged():
    """A camera.read() that RAISES (not a graceful (False, None) return)
    is caught by the inner try around that specific call and treated as
    a retriable frame failure -- identical to a graceful failure. After
    MAX_FRAME_FAILURES consecutive raises, the scanner gives up and
    records 'failed repeatedly', including the original exception text."""
    mock_cv2, mock_cap, mock_pkg, mock_dec = _make_mocks()
    mock_cap.isOpened.return_value = True
    mock_cap.read.side_effect = RuntimeError("synthetic scanner failure")
    mock_dec.decode.return_value = []

    with patch.dict("sys.modules", {"cv2": mock_cv2, "pyzbar": mock_pkg}):
        scanner = BarcodeScanner()
        assert scanner.start() is True

        deadline = time.monotonic() + 3.0
        error = None
        while error is None and time.monotonic() < deadline:
            error = scanner.error
            if error is None:
                time.sleep(0.01)

        assert error is not None, "expected the repeated failure to be recorded in .error"
        assert "failed repeatedly" in error.lower()
        assert "synthetic scanner failure" in error
        assert scanner.running is False
        assert scanner.available is False


def test_available_and_running_stay_consistent_on_repeated_failure():
    """If the scan loop dies from repeated graceful (False, None) frame
    failures, available must go False together with running."""
    mock_cv2, mock_cap, mock_pkg, mock_dec = _make_mocks()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (False, None)
    mock_dec.decode.return_value = []

    with patch.dict("sys.modules", {"cv2": mock_cv2, "pyzbar": mock_pkg}):
        scanner = BarcodeScanner()
        scanner.start()

        deadline = time.monotonic() + 2.0
        while scanner.running and time.monotonic() < deadline:
            time.sleep(0.01)

        assert scanner.running is False
        assert scanner.available is False
        assert scanner.error is not None


def test_stop_is_safe_to_call_multiple_times():
    """stop() should not raise even if called repeatedly, including on
    a scanner that never successfully started."""
    scanner = BarcodeScanner()
    scanner.stop()
    scanner.stop()


def test_stop_releases_camera():
    """stop() must actually call release() on the camera handle."""
    mock_cv2, mock_cap, mock_pkg, mock_dec = _make_mocks()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, MagicMock())
    mock_dec.decode.return_value = []

    with patch.dict("sys.modules", {"cv2": mock_cv2, "pyzbar": mock_pkg}):
        scanner = BarcodeScanner()
        scanner.start()
        time.sleep(0.1)
        scanner.stop()
        assert mock_cap.release.called


