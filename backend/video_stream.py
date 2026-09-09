"""
video_stream.py
---------------
Threaded video capture wrapper.
Always exposes the LATEST frame; drops stale frames so the processing
pipeline never builds a backlog.

Supports:
  - Laptop webcam  (source = 0)
  - HTTP/MJPEG URL (source = "http://...")
  - RTSP stream    (source = "rtsp://...")
"""
from __future__ import annotations

import threading
import time
import cv2


class VideoStream:
    def __init__(self):
        self._cap: cv2.VideoCapture | None = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self.error: str | None = None
        self.width: int = 640
        self.height: int = 480

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, source) -> bool:
        """
        Open the video source and start the background read thread.
        source: 0 (webcam) | "http://..." | "rtsp://..."
        Returns True on success.
        """
        self.stop()  # kill any previous stream

        self.error = None
        self._frame = None

        cap = cv2.VideoCapture(source)

        # For network streams give OpenCV a short timeout / buffer hint
        if isinstance(source, str):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            self.error = f"Cannot open source: {source}"
            return False

        self._cap = cap
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Stop the capture thread and release the device."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._frame = None

    def get_frame(self):
        """Return the most recent frame (BGR numpy array) or None."""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _read_loop(self):
        consecutive_failures = 0
        while self._running:
            if self._cap is None:
                break
            ret, frame = self._cap.read()
            if not ret:
                consecutive_failures += 1
                if consecutive_failures > 30:
                    self.error = "Stream ended or connection lost."
                    self._running = False
                    break
                time.sleep(0.05)
                continue
            consecutive_failures = 0
            with self._lock:
                self._frame = frame
