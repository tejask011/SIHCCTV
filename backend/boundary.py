"""
boundary.py
-----------
Virtual security boundary management.

The frontend sends polygon points as NORMALISED coordinates [0.0 .. 1.0]
relative to the displayed <img> element.

This module scales them to ACTUAL frame pixel coordinates so that the
point-in-polygon test uses the same coordinate space as YOLO detections.

Touch detection: a point is considered "in or touching" if it is inside
the polygon OR within TOUCH_PIXELS of any edge.
"""
from __future__ import annotations

import threading
import numpy as np
import cv2

TOUCH_PIXELS = 18   # pixels from boundary edge that counts as "touching"


class BoundaryManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._points_norm: list[list[float]] = []   # normalised [x, y]
        self._points_px:   list[list[int]]   = []   # pixel [x, y]
        self._frame_w: int = 640
        self._frame_h: int = 480

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_frame_size(self, w: int, h: int):
        with self._lock:
            self._frame_w = w
            self._frame_h = h
            self._recalc_pixels()

    def set_boundary(self, points_norm: list[list[float]]):
        """
        Accept normalised points from the frontend and convert to pixels.
        points_norm: [[x1,y1], [x2,y2], ...]  where each value is 0..1
        """
        with self._lock:
            self._points_norm = points_norm
            self._recalc_pixels()

    def clear(self):
        with self._lock:
            self._points_norm = []
            self._points_px   = []

    def get_points(self) -> list[list[float]]:
        with self._lock:
            return [list(p) for p in self._points_norm]

    def is_active(self) -> bool:
        with self._lock:
            return len(self._points_px) >= 3

    def is_inside_or_touching(self, point: tuple[int, int]) -> bool:
        """
        Returns True if pixel-space `point` (x, y) is:
          - inside the polygon, OR
          - within TOUCH_PIXELS of any polygon edge.
        Returns False if no boundary is set.
        """
        with self._lock:
            if len(self._points_px) < 3:
                return False
            poly = np.array(self._points_px, dtype=np.float32)
            # measureDist=True → signed distance; negative = outside, positive = inside
            dist = cv2.pointPolygonTest(poly, (float(point[0]), float(point[1])), True)
            # Inside (dist > 0) OR touching/near edge (dist >= -TOUCH_PIXELS)
            return dist >= -TOUCH_PIXELS

    def draw(self, frame: np.ndarray, alert_active: bool = False) -> np.ndarray:
        """
        Overlay the boundary polygon on the frame with a semi-transparent fill.
        When alert_active=True the zone pulses bright red.
        """
        with self._lock:
            pts = self._points_px.copy()

        if len(pts) < 2:
            return frame

        overlay = frame.copy()
        pts_arr = np.array(pts, dtype=np.int32)

        if len(pts) >= 3:
            fill_color = (0, 0, 220) if alert_active else (0, 0, 140)
            alpha      = 0.45       if alert_active else 0.20
            cv2.fillPoly(overlay, [pts_arr], fill_color)
            cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # Edge color: bright red on alert, normal red otherwise
        edge_color = (0, 0, 255) if alert_active else (0, 60, 220)
        thickness  = 3 if alert_active else 2

        for i in range(len(pts)):
            p1 = tuple(pts[i])
            p2 = tuple(pts[(i + 1) % len(pts)])
            cv2.line(frame, p1, p2, edge_color, thickness)

        # Vertex dots
        for p in pts:
            cv2.circle(frame, tuple(p), 5, edge_color, -1)

        # Label
        if len(pts) >= 3:
            cx = int(sum(p[0] for p in pts) / len(pts))
            cy = int(sum(p[1] for p in pts) / len(pts))
            label = "⚠ BREACH" if alert_active else "SECURITY ZONE"
            color = (0, 0, 255) if alert_active else (80, 80, 255)
            cv2.putText(
                frame, label,
                (cx - 55, cy),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                color, 2, cv2.LINE_AA,
            )

        return frame

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recalc_pixels(self):
        """Convert stored normalised points to pixel coords. Must hold lock."""
        self._points_px = [
            [int(p[0] * self._frame_w), int(p[1] * self._frame_h)]
            for p in self._points_norm
        ]
