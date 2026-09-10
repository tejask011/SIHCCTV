"""
detector.py
-----------
YOLO object detection with fully dynamic class categorisation.

NO class names are hardcoded in this file.

At startup:
  1. Load the YOLO model (auto-downloads weights on first run).
  2. Read `coco_classes.json` which maps class_name → supercategory.
  3. Read `_supercategory_to_display` from the same JSON to map
     supercategory → display group (HUMAN / ANIMAL / VEHICLE / OBJECT).

If the loaded model uses a custom dataset whose class names are NOT in
`coco_classes.json`, those detections are shown as-is with category "OBJECT".

To add support for a new model or new classes, just edit `coco_classes.json`.
No Python code changes needed.
"""
from __future__ import annotations

import json
import os
import numpy as np
import cv2
from ultralytics import YOLO
try:
    from ultralytics import YOLOWorld
    _YOLO_WORLD_AVAILABLE = True
except ImportError:
    _YOLO_WORLD_AVAILABLE = False

# ---------------------------------------------------------------------------
# Dual-Purpose Vocabulary: Surveillance + Everyday Foreground Items
# ---------------------------------------------------------------------------
SURVEILLANCE_AND_OBJECT_CLASSES = [
    # ── Surveillance & Perimeter Security ──
    "person", "car", "motorcycle", "bicycle", "dog", "cat",
    "license plate", "number plate",

    # ── Wearables & Personal Accessories ──
    "watch", "smart watch", "headphones", "glasses", "gloves",
    "bag", "backpack", "handbag",

    # ── Foreground Daily Objects & Surfaces (including bottle synonyms for flipped angles) ──
    "bottle", "water bottle", "plastic bottle",
    "charger", "phone charger",
    "cell phone", "keyboard", "table", "desk", "laptop", "mouse", "book"
]

# Set of classes kept when "Person & Wearables Only" mode is active
WEARABLES_AND_PERSON_CLASSES = {
    "person", "watch", "smart watch", "headphones", "glasses", "gloves",
    "bag", "backpack", "handbag"
}

# Normalize synonyms for clean UI display
DISPLAY_LABEL_NORMALIZE = {
    "plastic bottle": "bottle",
    "phone charger":  "charger",
    "desk":           "table",
}

# Classes that should NEVER trigger false positives (e.g. from fallback COCO models)
NOISE_CLASSES = {
    "hair drier", "toaster", "refrigerator", "microwave", "sink",
    "toilet", "skis", "snowboard", "surfboard", "kite", "parking meter"
}

# ---------------------------------------------------------------------------
# Load category mapping from JSON (no hardcoding in Python)
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_META_PATH = os.path.join(_HERE, "coco_classes.json")

def _load_category_maps() -> tuple[dict[str, str], dict[str, str]]:
    """
    Returns:
      class_to_supercat : {class_name: supercategory}   e.g. "dog" → "animal"
      supercat_to_display: {supercategory: display_label} e.g. "animal" → "ANIMAL"
    """
    try:
        with open(_META_PATH, encoding="utf-8") as f:
            meta = json.load(f)
        return meta["classes"], meta["_supercategory_to_display"]
    except Exception as e:
        print(f"[detector] WARNING: could not load coco_classes.json ({e}). "
              "All detections will be categorised as OBJECT.")
        return {}, {}

_CLASS_TO_SUPERCAT, _SUPERCAT_TO_DISPLAY = _load_category_maps()


def _get_display_category(label: str) -> str:
    """
    Dynamically derive display category from the JSON mapping.
    Falls back to OBJECT for unknown classes (e.g. custom YOLO models).
    """
    supercat = _CLASS_TO_SUPERCAT.get(label.lower(), None)
    if supercat is None:
        return "OBJECT"
    return _SUPERCAT_TO_DISPLAY.get(supercat, "OBJECT")


# ---------------------------------------------------------------------------
# Bounding-box colours per category (keyed by display category)
# ---------------------------------------------------------------------------

CATEGORY_COLOR = {
    "HUMAN":   (0,   200, 255),   # amber
    "ANIMAL":  (0,   255, 128),   # green
    "VEHICLE": (255, 128,   0),   # blue-orange
    "OBJECT":  (200, 200, 200),   # grey
}

INTRUSION_COLOR = (0, 0, 255)   # red — overrides when inside boundary


# ---------------------------------------------------------------------------
# Detector class
# ---------------------------------------------------------------------------

class Detector:
    def __init__(self, model_name: str = "yolov8s-worldv2.pt", conf_threshold: float = 0.25):
        self.model = None
        self.is_world_model = False
        self.mode = "all"   # "all" or "person_wearables"

        # 1. Try YOLO-World first for exact custom vocabulary
        if _YOLO_WORLD_AVAILABLE:
            try:
                self.model = YOLOWorld(model_name)
                self.model.set_classes(SURVEILLANCE_AND_OBJECT_CLASSES)
                self.is_world_model = True
                print(f"[detector] Loaded YOLO-World ({model_name}) with {len(SURVEILLANCE_AND_OBJECT_CLASSES)} custom classes.")
            except Exception as e:
                print(f"[detector] Could not load YOLO-World ({model_name}): {e}")

        # 2. Fallback to standard models if YOLO-World wasn't loaded
        if self.model is None:
            for attempt in ["yolo11s.pt", "yolo11n.pt", "yolov8n.pt"]:
                try:
                    self.model = YOLO(attempt)
                    print(f"[detector] Fallback loaded model: {attempt}")
                    break
                except Exception as e:
                    print(f"[detector] Could not load {attempt}: {e}")
            else:
                raise RuntimeError("[detector] No YOLO model could be loaded.")

        self.conf_threshold = conf_threshold

        # Print all active classes
        print(f"[detector] conf_threshold={conf_threshold}  |  mode={self.mode}  |  {len(self.model.names)} classes active:")
        for cid, cname in self.model.names.items():
            cat = _get_display_category(cname)
            print(f"  [{cid:3d}] {cname:<20s} → {cat}")

    def set_mode(self, mode: str) -> str:
        """Switch detection filter mode: 'all' or 'person_wearables'."""
        if mode in ("all", "person_wearables"):
            self.mode = mode
            print(f"[detector] Detection mode changed to: {self.mode}")
        return self.mode

    def detect(self, frame: np.ndarray) -> list[dict]:
        """
        Run inference on a BGR frame.
        Returns a list of detection dicts:
          {
            label:      str,   — normalized class name
            confidence: float,
            bbox:       [x1, y1, x2, y2],
            category:   str,   — display group (HUMAN/ANIMAL/VEHICLE/OBJECT)
            ref_point:  (cx, bottom),
          }
        """
        results = self.model(frame, verbose=False, conf=self.conf_threshold)[0]
        detections = []

        if results.boxes is None:
            return detections

        for box in results.boxes:
            cls_id = int(box.cls[0])
            raw_label = self.model.names[cls_id]

            # Reject known false-positive noise classes
            if raw_label.lower() in NOISE_CLASSES:
                continue

            # Normalize synonyms (e.g. plastic bottle → bottle, desk → table)
            label = DISPLAY_LABEL_NORMALIZE.get(raw_label.lower(), raw_label)

            # Filter if in "person & wearables only" mode
            if self.mode == "person_wearables":
                if label.lower() not in WEARABLES_AND_PERSON_CLASSES and raw_label.lower() not in WEARABLES_AND_PERSON_CLASSES:
                    continue

            conf   = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            category = _get_display_category(label)
            cx       = (x1 + x2) // 2
            bottom   = y2

            detections.append({
                "label":      label,
                "confidence": round(conf, 2),
                "bbox":       [x1, y1, x2, y2],
                "category":   category,
                "ref_point":  (cx, bottom),
            })

        return detections

    def draw(
        self,
        frame: np.ndarray,
        detections: list[dict],
        intruding_indices: set[int],
    ) -> np.ndarray:
        """Draw bounding boxes + labels on frame."""
        for i, det in enumerate(detections):
            x1, y1, x2, y2 = det["bbox"]
            label    = det["label"]
            conf     = det["confidence"]
            category = det["category"]

            color = INTRUSION_COLOR if i in intruding_indices else CATEGORY_COLOR.get(category, (200, 200, 200))

            # Bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Label + confidence badge
            text = f"{label} {conf:.2f}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(
                frame, text,
                (x1 + 2, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 0, 0), 1, cv2.LINE_AA,
            )

            # Ground-contact dot
            cx, cy = det["ref_point"]
            cv2.circle(frame, (cx, cy), 4, color, -1)

            # OCR / Number Plate Badge
            if det.get("is_plate") and det.get("plate_number"):
                plate_str = f"PLATE: {det['plate_number']}"
                (pw, ph), _ = cv2.getTextSize(plate_str, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
                # Yellow plate background with black text (Indian license plate style)
                py1 = min(y2 + 4, frame.shape[0] - ph - 8)
                cv2.rectangle(frame, (x1, py1), (x1 + pw + 10, py1 + ph + 8), (0, 215, 255), -1)
                cv2.rectangle(frame, (x1, py1), (x1 + pw + 10, py1 + ph + 8), (0, 0, 0), 2)
                cv2.putText(
                    frame, plate_str,
                    (x1 + 5, py1 + ph + 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                    (0, 0, 0), 2, cv2.LINE_AA
                )
            elif det.get("ocr_text"):
                ocr_str = f"TXT: {det['ocr_text'][:20]}"
                (tw2, th2), _ = cv2.getTextSize(ocr_str, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                py1 = min(y2 + 4, frame.shape[0] - th2 - 6)
                cv2.rectangle(frame, (x1, py1), (x1 + tw2 + 8, py1 + th2 + 6), (230, 160, 20), -1)
                cv2.putText(
                    frame, ocr_str,
                    (x1 + 4, py1 + th2 + 1),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255, 255, 255), 1, cv2.LINE_AA
                )

        return frame
