"""
detection_log.py
-----------------
Rolling log of every object YOLO detects (not just intrusions).

Each log entry:
  {
    "id":         int,            # ms timestamp — unique enough
    "time":       str,            # "HH:MM:SS"
    "label":      str,            # raw YOLO class name  e.g. "cell phone"
    "category":   str,            # display group        e.g. "OBJECT"
    "confidence": float,          # 0..1
    "intruding":  bool,           # was it inside the boundary?
    "emoji":      str,
  }

Entries are deduped so the same class doesn't spam every frame.
A new log entry is only written when:
  - A class appears for the first time, OR
  - A class disappears and then reappears (COOLDOWN_SEC gap).
"""
from __future__ import annotations

import time
import threading
from datetime import datetime

MAX_ENTRIES  = 200      # rolling window size
COOLDOWN_SEC = 8.0      # minimum seconds between repeated log entries for same label

_EMOJI = {
    "HUMAN":      "🧍",
    "ANIMAL":     "🐾",
    "VEHICLE":    "🚗",
    "OBJECT":     "📦",
    "NO. PLATES": "🚘",
    "TAMPER":     "🚫",
}


class DetectionLog:
    def __init__(self):
        self._lock    = threading.Lock()
        self._entries: list[dict] = []
        # label → last time it was logged
        self._last_seen: dict[str, float] = {}
        # label → last time it was actually visible in frame
        self._visible_at: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, detections: list[dict], intruding_indices: set[int]) -> list[dict]:
        """
        Call every processed frame.
        Returns a list of NEW log entries created this call.
        """
        now        = time.time()
        new_entries = []

        seen_labels: set[str] = set()

        for i, det in enumerate(detections):
            label     = det["label"]
            category  = det["category"]
            conf      = det["confidence"]
            intruding = i in intruding_indices

            seen_labels.add(label)
            self._visible_at[label] = now

            last = self._last_seen.get(label, 0.0)
            if now - last >= COOLDOWN_SEC:
                entry = {
                    "id":         int(now * 1000),
                    "time":       datetime.now().strftime("%H:%M:%S"),
                    "label":      label,
                    "category":   category,
                    "confidence": conf,
                    "intruding":  intruding,
                    "emoji":      _EMOJI.get(category, "🔍"),
                }
                with self._lock:
                    self._entries.append(entry)
                    if len(self._entries) > MAX_ENTRIES:
                        self._entries = self._entries[-MAX_ENTRIES:]
                self._last_seen[label] = now
                new_entries.append(entry)

        # Reset cooldown only for labels that have disappeared for at least 3 seconds
        # (prevents frame jitter / momentary flicker from spamming new log entries)
        gone = set(self._last_seen.keys()) - seen_labels
        for label in gone:
            if now - self._visible_at.get(label, 0.0) >= 3.0:
                del self._last_seen[label]

        return new_entries

    def get_all(self) -> list[dict]:
        """Return all entries newest-first."""
        with self._lock:
            return list(reversed(self._entries))

    def clear(self):
        with self._lock:
            self._entries.clear()
            now = time.time()
            # Mark currently tracked labels as seen now so they don't immediately re-spam
            for lbl in list(self._last_seen.keys()):
                self._last_seen[lbl] = now

    def add_custom_entry(self, label: str, category: str = "TAMPER", confidence: float = 1.0, intruding: bool = True, emoji: str = "🚫") -> dict:
        now = time.time()
        entry = {
            "id":         int(now * 1000),
            "time":       datetime.now().strftime("%H:%M:%S"),
            "label":      label,
            "category":   category,
            "confidence": confidence,
            "intruding":  intruding,
            "emoji":      emoji,
        }
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > MAX_ENTRIES:
                self._entries = self._entries[-MAX_ENTRIES:]
        return entry

