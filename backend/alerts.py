"""
alerts.py
---------
Intrusion alert management — 5-second continuous dwell timer.

Rules:
  - An alert fires ONLY when a detection has been INSIDE (or touching)
    the boundary CONTINUOUSLY for >= DWELL_SEC seconds.
  - While the object is still inside after the alert, NO further alerts fire.
  - The moment the object LEAVES the boundary, its timer resets.
  - If it re-enters, the 5-second countdown starts again from zero.
  - Keeps a rolling list of the last MAX_ALERTS alerts for the dashboard.
"""
from __future__ import annotations

import time
import threading
from datetime import datetime


DWELL_SEC  = 5       # seconds of continuous presence before alert fires
MAX_ALERTS = 50      # maximum alerts to keep in memory


class AlertManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._alerts: list[dict] = []

        # Per-slot state:
        # slot_key -> {
        #   "entry_time": float | None,   # time object first entered zone
        #   "alerted":    bool,           # already fired for this stay
        # }
        self._state: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, detections: list[dict], intruding_indices: set[int]) -> list[dict]:
        """
        Update dwell timers and fire alerts for detections that have been
        inside the zone continuously for >= DWELL_SEC seconds.
        Returns the list of NEW alerts created this call.
        """
        new_alerts = []
        now = time.time()

        for i, det in enumerate(detections):
            key    = self._slot_key(det)
            inside = i in intruding_indices

            with self._lock:
                state = self._state.get(key, {"entry_time": None, "alerted": False})

                if inside:
                    if state["entry_time"] is None:
                        # Just entered — start timer
                        state = {"entry_time": now, "alerted": False}
                    else:
                        dwell = now - state["entry_time"]
                        if dwell >= DWELL_SEC and not state["alerted"]:
                            # 5-second threshold crossed — fire alert
                            alert = self._make_alert(det, dwell)
                            self._alerts.append(alert)
                            if len(self._alerts) > MAX_ALERTS:
                                self._alerts = self._alerts[-MAX_ALERTS:]
                            new_alerts.append(alert)
                            state = {"entry_time": state["entry_time"], "alerted": True}
                else:
                    # Object left the zone — reset so next entry starts fresh
                    state = {"entry_time": None, "alerted": False}

                self._state[key] = state

        return new_alerts

    def get_dwell_times(self, detections: list[dict], intruding_indices: set[int]) -> dict[int, float]:
        """
        Returns a mapping of detection index → dwell seconds (for UI progress).
        Only includes detections currently inside.
        """
        now    = time.time()
        result = {}
        for i, det in enumerate(detections):
            if i not in intruding_indices:
                continue
            key   = self._slot_key(det)
            state = self._state.get(key, {"entry_time": None})
            if state["entry_time"] is not None:
                result[i] = min(now - state["entry_time"], DWELL_SEC)
        return result

    def get_all(self) -> list[dict]:
        with self._lock:
            return list(reversed(self._alerts))  # newest first

    def clear(self):
        with self._lock:
            self._alerts.clear()
            self._state.clear()

    def add_custom_alert(self, title: str, message: str, category: str = "TAMPER", emoji: str = "🚨") -> dict:
        now = time.time()
        alert = {
            "id":       int(now * 1000),
            "emoji":    emoji,
            "title":    title,
            "message":  message,
            "category": category,
            "time":     datetime.now().strftime("%H:%M:%S"),
        }
        with self._lock:
            self._alerts.append(alert)
            if len(self._alerts) > MAX_ALERTS:
                self._alerts = self._alerts[-MAX_ALERTS:]
        return alert

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _slot_key(det: dict) -> str:
        """
        Coarse grid bucket so nearby bboxes of same class share a slot.
        Grid cell = 80px.
        """
        cx, cy = det["ref_point"]
        return f"{det['label']}_{cx // 80}_{cy // 80}"

    @staticmethod
    def _make_alert(det: dict, dwell: float) -> dict:
        emoji_map = {
            "HUMAN":   "🚨",
            "ANIMAL":  "🐾",
            "VEHICLE": "🚗",
            "OBJECT":  "📦",
        }
        emoji = emoji_map.get(det["category"], "⚠️")
        label = det["label"].capitalize()

        ocr_text = det.get("ocr_text", "")
        is_plate = det.get("is_plate", False)
        plate_number = det.get("plate_number", "")

        if is_plate and plate_number:
            msg = f"{label} [Plate: {plate_number}] in restricted zone for {dwell:.1f}s"
            emoji = "🚔"
        elif ocr_text:
            msg = f"{label} (\"{ocr_text[:24]}\") in restricted zone for {dwell:.1f}s"
        else:
            msg = f"{label} in restricted zone for {dwell:.1f}s"

        return {
            "id":           int(time.time() * 1000),
            "emoji":        emoji,
            "title":        "ANPR / INTRUSION ALERT" if is_plate else "INTRUSION ALERT",
            "message":      msg,
            "category":     det["category"],
            "label":        det["label"],
            "confidence":   det.get("confidence", 0.9),
            "bbox":         det.get("bbox"),
            "ref_point":    det.get("ref_point"),
            "ocr_text":     ocr_text,
            "is_plate":     is_plate,
            "plate_number": plate_number,
            "time":         datetime.now().strftime("%H:%M:%S"),
        }
