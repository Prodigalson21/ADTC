"""
barcode_scanner.py -- Webcam barcode/QR scanner interface.

Uses OpenCV for webcam capture and pyzbar for barcode decoding.

The scanner is designed to degrade gracefully:
- Missing cv2/pyzbar dependencies do not crash the application.
- Missing/unavailable webcam returns False from start().
- Transient webcam frame failures are retried.
- Repeated frame failures stop the scanner and expose an error.
- Runtime errors are logged and exposed through .error.
- Duplicate barcode reads are debounced.
- A daemon thread prevents scanner shutdown from blocking process exit.

Public API:
    scanner = BarcodeScanner()
    scanner.start()
    value = scanner.get_latest()
    scanner.stop()
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional


class BarcodeScanner:
    """Background webcam barcode/QR scanner."""

    MAX_FRAME_FAILURES = 10
    FRAME_RETRY_DELAY = 0.05
    DEFAULT_CAMERA_INDEX = 0
    DEFAULT_DEBOUNCE_SECONDS = 2.0

    def __init__(
        self,
        camera_index: int = DEFAULT_CAMERA_INDEX,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
    ) -> None:
        if debounce_seconds < 0:
            raise ValueError("debounce_seconds must be >= 0")

        self.camera_index = camera_index
        self.debounce_seconds = debounce_seconds

        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        self._thread: Optional[threading.Thread] = None
        self._camera: Any = None

        self._available = False
        self._running = False
        self._error: Optional[str] = None
        self._latest: Optional[str] = None

        # Maps barcode value -> last accepted monotonic timestamp.
        self._last_seen: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return True when the scanner is currently operational."""
        with self._lock:
            return self._available

    @property
    def running(self) -> bool:
        """Return True while the scanner worker thread is running."""
        with self._lock:
            return self._running

    @property
    def error(self) -> Optional[str]:
        """Return the most recent scanner error, if any."""
        with self._lock:
            return self._error

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """
        Start the scanner.

        Returns:
            True if the webcam was opened and the worker started.
            False if dependencies or webcam are unavailable.
        """
        with self._lock:
            if self._running:
                return True

            self._error = None
            self._latest = None
            self._stop_event.clear()

        try:
            import cv2
            from pyzbar import pyzbar
        except (ImportError, ModuleNotFoundError) as exc:
            with self._lock:
                self._available = False
                self._running = False
                self._error = f"Barcode scanner dependencies unavailable: {exc}"
            return False

        try:
            camera = cv2.VideoCapture(self.camera_index)
        except Exception as exc:
            logging.exception("Failed to open barcode scanner webcam")

            with self._lock:
                self._available = False
                self._running = False
                self._error = f"Webcam initialization failed: {exc}"

            return False

        try:
            if not camera.isOpened():
                with self._lock:
                    self._available = False
                    self._running = False
                    self._error = "Webcam unavailable"

                try:
                    camera.release()
                except Exception:
                    logging.exception("Failed to release unavailable webcam")

                return False
        except Exception as exc:
            logging.exception("Failed while checking webcam state")

            with self._lock:
                self._available = False
                self._running = False
                self._error = f"Webcam initialization failed: {exc}"

            try:
                camera.release()
            except Exception:
                logging.exception("Failed to release webcam after initialization error")

            return False

        with self._lock:
            self._camera = camera
            self._available = True
            self._running = True

        self._thread = threading.Thread(
            target=self._scan_loop,
            args=(camera, cv2, pyzbar),
            name="barcode-scanner",
            daemon=True,
        )

        try:
            self._thread.start()
        except Exception as exc:
            logging.exception("Failed to start barcode scanner thread")

            with self._lock:
                self._running = False
                self._available = False
                self._error = f"Barcode scanner thread failed to start: {exc}"
                self._camera = None

            try:
                camera.release()
            except Exception:
                logging.exception("Failed to release webcam after thread failure")

            return False

        return True

    def stop(self) -> None:
        """Stop the scanner and release the webcam."""
        self._stop_event.set()

        thread = self._thread

        if thread is not None and thread.is_alive():
            # The worker has a short retry delay, so this should normally
            # return quickly.
            thread.join(timeout=2.0)

        camera = None

        with self._lock:
            camera = self._camera
            self._camera = None
            self._running = False
            self._available = False

        if camera is not None:
            try:
                camera.release()
            except Exception:
                logging.exception("Failed to release barcode scanner webcam")

        self._thread = None

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def get_latest(self, clear: bool = False) -> Optional[str]:
        """
        Return the most recently accepted barcode.

        Args:
            clear: If True, consume the current value.

        Returns:
            Barcode/QR value, or None if no value is waiting.
        """
        with self._lock:
            value = self._latest

            if clear:
                self._latest = None

            return value

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _scan_loop(self, camera: Any, cv2: Any, pyzbar: Any) -> None:
        """Capture frames and decode barcodes until stopped."""
        consecutive_failures = 0

        try:
            while not self._stop_event.is_set():
                try:
                    success, frame = camera.read()
                except Exception as exc:
                    logging.exception("Webcam frame capture failure")

                    consecutive_failures += 1

                    if consecutive_failures >= self.MAX_FRAME_FAILURES:
                        with self._lock:
                            self._error = (
                                "Webcam frame capture failed repeatedly: "
                                f"{exc}"
                            )
                        break

                    time.sleep(self.FRAME_RETRY_DELAY)
                    continue

                if not success or frame is None:
                    consecutive_failures += 1

                    if consecutive_failures >= self.MAX_FRAME_FAILURES:
                        with self._lock:
                            self._error = (
                                "Webcam frame capture failed repeatedly"
                            )
                        break

                    time.sleep(self.FRAME_RETRY_DELAY)
                    continue

                consecutive_failures = 0

                # Decode failures are isolated from the outer worker loop.
                # This prevents a decoder problem from killing the scanner.
                try:
                    decoded_objects = pyzbar.decode(frame)
                except Exception:
                    logging.exception("Barcode decode failure")
                    continue

                now = time.monotonic()

                for obj in decoded_objects:
                    try:
                        raw_data = obj.data
                        value = raw_data.decode("utf-8").strip()
                    except (UnicodeDecodeError, AttributeError, TypeError):
                        # Ignore malformed barcode payloads and continue
                        # processing other objects in the same frame.
                        continue

                    if not value:
                        continue

                    # Debounce check + mutation are performed under the same
                    # lock so two scanner operations cannot accept the same
                    # value concurrently.
                    with self._lock:
                        previous = self._last_seen.get(value)

                        if (
                            previous is not None
                            and now - previous < self.debounce_seconds
                        ):
                            continue

                        self._last_seen[value] = now
                        self._latest = value

                        # Prevent unbounded growth of _last_seen.
                        cutoff = now - self.debounce_seconds

                        if len(self._last_seen) > 1000:
                            self._last_seen = {
                                key: timestamp
                                for key, timestamp in self._last_seen.items()
                                if timestamp >= cutoff
                            }

        except Exception as exc:
            logging.exception("Barcode scanner runtime error")

            with self._lock:
                self._error = f"Barcode scanner runtime error: {exc}"

        finally:
            # Camera ownership belongs to stop().
            #
            # We deliberately do NOT call camera.release() here. This avoids
            # two different code paths racing to release the same camera.
            #
            # If the worker exits unexpectedly, however, the scanner is no
            # longer operational. Therefore both flags must be cleared.
            with self._lock:
                self._running = False
                self._available = False
