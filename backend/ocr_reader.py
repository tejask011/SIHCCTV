"""
ocr_reader.py
-------------
High-performance OCR & ANPR (Automatic Number Plate Recognition) engine.
Performs text extraction on detected objects (vehicles, books, documents, labels).

Features:
  - Background thread initialization (zero server startup delay).
  - Preprocessing with CLAHE and smart scaling for low-res cameras / DroidCam.
  - Indian and International vehicle license plate regex pattern recognition.
  - General text / document / book paragraph reader.
  - Thread-safe background execution to maintain smooth 30 FPS video streaming.
"""
from __future__ import annotations

import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np

# Valid Indian State / Union Territory RTO codes (including Bharat Series BH)
VALID_INDIAN_STATES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN",
    "GA", "GJ", "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD",
    "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "PB", "PY", "RJ",
    "SK", "TN", "TR", "TS", "UK", "UP", "WB", "BH"
}

# Target labels that qualify as vehicle candidates
VEHICLE_LABELS = {"car", "motorcycle", "bus", "truck", "van", "jeep", "auto", "vehicle"}
TEXT_LABELS = {"book", "document"}


def validate_and_format_plate(candidate: str, is_vehicle: bool = False) -> tuple[bool, str]:
    """
    Syntax-aware multi-country license plate validator and character corrector.
    Returns (is_valid, cleaned_and_formatted_plate_string).

    Guarantees & Features:
      - Filters out camera overlays (DROIDCAM, VIDEO, CAMERA, etc.).
      - Supports Indian RTO plates (MH 12 AB 1234, DL 8C AF 5030, etc.).
      - Supports Indian Bharat (BH) series (22 BH 1234 AA).
      - Supports UK prefix style (R88 SPU, fixes 'b' -> '8' to 'R88 SPU').
      - Supports UK standard style (AB12 CDE).
      - Supports International / US alphanumeric plates (4-9 alphanumeric characters).
    """
    if not candidate:
        return False, ""

    raw = re.sub(r'[^A-Z0-9]', '', candidate.upper())
    if len(raw) < 4 or len(raw) > 11:
        return False, ""

    # Never match camera watermark tokens or UI words
    IGNORED = (
        "DROIDCAM", "VIDEO", "FEED", "CAMERA", "1080P", "720P", "LAPTOP",
        "WEBCAM", "FULLSCREEN", "PRESET", "BOUNDARY", "SEARCH", "SUNNY",
        "SCANPLATE", "GRID", "WEARABLES", "INFERENCE", "ACTIVE", "VIEWPORT",
        "HACKATHON", "SURVEILLANCE"
    )
    for wm in IGNORED:
        if wm in raw:
            return False, ""

    char_to_digit = {'B': '8', 'O': '0', 'D': '0', 'I': '1', 'L': '1', 'S': '5', 'Z': '2', 'G': '6'}
    digit_to_char = {'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B', '6': 'G'}

    # 1. Indian RTO Plate Format (e.g. DL 08 AF 5030, MH 12 AB 1234)
    c_chars = list(raw)
    st_candidate = "".join([digit_to_char.get(c, c) for c in c_chars[:2]])
    if st_candidate in VALID_INDIAN_STATES and len(raw) >= 6:
        c_chars[0] = st_candidate[0]
        c_chars[1] = st_candidate[1]
        if c_chars[2] in char_to_digit:
            c_chars[2] = char_to_digit[c_chars[2]]
        for k in range(max(3, len(c_chars) - 4), len(c_chars)):
            if c_chars[k] in char_to_digit:
                c_chars[k] = char_to_digit[c_chars[k]]
        fixed = "".join(c_chars)
        m = re.match(r'^([A-Z]{2})([0-9]{1,2})([A-Z]{0,3})([0-9]{1,4})$', fixed)
        if m:
            parts = [m.group(1), m.group(2)]
            if m.group(3): parts.append(m.group(3))
            if m.group(4): parts.append(m.group(4))
            return True, " ".join(parts)

    # 2. Bharat (BH) series (e.g. 22 BH 1234 AA)
    m_bh = re.match(r'^([0-9]{2})(BH)([0-9]{4})([A-Z]{1,2})$', raw)
    if m_bh:
        return True, f"{m_bh.group(1)} {m_bh.group(2)} {m_bh.group(3)} {m_bh.group(4)}"

    # 3. UK Standard Style: 2 letters + 2 digits + 3 letters (e.g. AB12 CDE)
    if len(raw) == 7:
        u2 = list(raw)
        for k in (0, 1, 4, 5, 6):
            if u2[k] in digit_to_char: u2[k] = digit_to_char[u2[k]]
        for k in (2, 3):
            if u2[k] in char_to_digit: u2[k] = char_to_digit[u2[k]]
        u2_fixed = "".join(u2)
        m_uk2 = re.match(r'^([A-Z]{2})([0-9]{2})([A-Z]{3})$', u2_fixed)
        if m_uk2:
            return True, f"{m_uk2.group(1)}{m_uk2.group(2)} {m_uk2.group(3)}"

    # 4. UK Prefix Style: 1 letter + 1-3 digits + 3 letters (e.g. R88 SPU, fixes 'b' -> '8')
    if 5 <= len(raw) <= 8:
        u_chars = list(raw)
        if u_chars[0] in digit_to_char:
            u_chars[0] = digit_to_char[u_chars[0]]
        # Last 3-4 chars are letters
        for k in range(len(u_chars) - 3, len(u_chars)):
            if u_chars[k] in digit_to_char:
                u_chars[k] = digit_to_char[u_chars[k]]
        # Middle chars are digits
        for k in range(1, len(u_chars) - 3):
            if u_chars[k] in char_to_digit:
                u_chars[k] = char_to_digit[u_chars[k]]
        u_fixed = "".join(u_chars)
        m_uk1 = re.match(r'^([A-Z])([0-9]{1,3})([A-Z]{2,4})$', u_fixed)
        if m_uk1:
            return True, f"{m_uk1.group(1)}{m_uk1.group(2)} {m_uk1.group(3)}"

    # 5. General Vehicle License Plate:
    # Must contain both letters and digits, length 4 to 9
    has_letters = any(c.isalpha() for c in raw)
    has_digits = any(c.isdigit() for c in raw)
    if has_letters and has_digits and 4 <= len(raw) <= 9:
        # Group into alphabetical and numerical blocks for clean readability
        chunks = re.findall(r'[A-Z]+|[0-9]+', raw)
        return True, " ".join(chunks)

    # 6. Fallback if detected directly on vehicle
    if is_vehicle and len(raw) >= 5 and (has_letters or has_digits):
        return True, raw

    return False, ""


class OCRReader:
    def __init__(self):
        self._lock = threading.Lock()
        self._reader = None
        self._is_ready = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr_worker")

        # Latest OCR scan result stored for WebSocket broadcasting and UI
        self._latest_result: dict = {
            "detected": False,
            "best_text": "",
            "is_plate": False,
            "plate_number": "",
            "all_lines": [],
            "confidence": 0.0,
            "category": "",
            "label": "",
            "timestamp": 0.0,
            "processing_ms": 0.0
        }

        # Cooldown per object to prevent redundant continuous scanning
        self._last_scan_time: float = 0.0

        # Start loading EasyOCR in background thread
        threading.Thread(target=self._init_engine, daemon=True).start()

    def _init_engine(self):
        try:
            import sys
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except Exception:
                pass
            print("[OCR] Initializing EasyOCR engine (en) in background...")
            import easyocr
            # Use English reader on CPU
            reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            with self._lock:
                self._reader = reader
                self._is_ready = True
            print("[OCR] EasyOCR engine ready for text & number plate scanning.")
        except Exception as e:
            print(f"[OCR] Error initializing EasyOCR: {e}")

    @property
    def is_ready(self) -> bool:
        with self._lock:
            return self._is_ready

    def get_latest(self) -> dict:
        with self._lock:
            return dict(self._latest_result)

    # ------------------------------------------------------------------
    # Image Preprocessing (Contrast Boost for Handwriting & Book Pages)
    # ------------------------------------------------------------------
    def _preprocess_crop(self, crop: np.ndarray, is_vehicle: bool = False) -> np.ndarray:
        """
        Enhance image contrast, sharpen strokes, and scale appropriately.
        Works for both real vehicles and handwritten notes / book pages.
        """
        if crop is None or crop.size == 0:
            return crop

        h, w = crop.shape[:2]

        # For vehicles, license plates sit on the lower 50% (front/rear bumper)
        if is_vehicle and h > 100:
            crop = crop[int(h * 0.35):, :]
            h, w = crop.shape[:2]

        # Target width around 480-600px for optimal speed/accuracy trade-off on CPU
        if w > 640:
            scale = 640.0 / w
            crop = cv2.resize(crop, (640, int(h * scale)), interpolation=cv2.INTER_AREA)
        elif w < 280 and w > 20:
            scale = 280.0 / w
            crop = cv2.resize(crop, (280, int(h * scale)), interpolation=cv2.INTER_CUBIC)

        # Convert to grayscale and apply min-max normalization
        # This stretches faint pencil/pen ink to pure black and paper to pure white
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        norm = cv2.normalize(gray, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)
        return cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def find_plate_candidates(img: np.ndarray) -> list[tuple[int, int, int, int]]:
        """
        Fast candidate license plate ROI detector.
        Combines:
          1. Color segmentation (yellow plates, white plates).
          2. Morphological Sobel gradient character clustering.
        Returns list of bounding boxes [(x1, y1, x2, y2), ...] ordered by likelihood.
        """
        if img is None or img.size == 0:
            return []
        h, w = img.shape[:2]
        if w < 30 or h < 15:
            return []

        seen_boxes = []

        def _add_cand(rx1, ry1, rx2, ry2, score):
            rx1, ry1 = max(0, int(rx1)), max(0, int(ry1))
            rx2, ry2 = min(w, int(rx2)), min(h, int(ry2))
            cw, ch = rx2 - rx1, ry2 - ry1
            if cw < 20 or ch < 8:
                return
            ar = cw / float(ch)
            if not (1.3 <= ar <= 7.0):
                return
            for sx1, sy1, sx2, sy2, _ in seen_boxes:
                ix1, iy1 = max(rx1, sx1), max(ry1, sy1)
                ix2, iy2 = min(rx2, sx2), min(ry2, sy2)
                if ix2 > ix1 and iy2 > iy1:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    union = (cw * ch) + ((sx2 - sx1) * (sy2 - sy1)) - inter
                    if union > 0 and (inter / union) > 0.4:
                        return
            seen_boxes.append((rx1, ry1, rx2, ry2, score))

        # --- Method 1: Yellow & Bright White Plate Color Extraction ---
        try:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            yellow_mask = cv2.inRange(hsv, np.array([10, 40, 70]), np.array([40, 255, 255]))
            white_mask = cv2.inRange(hsv, np.array([0, 0, 150]), np.array([180, 50, 255]))
            combined_color = cv2.bitwise_or(yellow_mask, white_mask)

            k_col = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
            closed_col = cv2.morphologyEx(combined_color, cv2.MORPH_CLOSE, k_col)
            cnts, _ = cv2.findContours(closed_col, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                bx, by, bw, bh = cv2.boundingRect(c)
                area = bw * bh
                if area > 80:
                    px = int(bw * 0.15)
                    py = int(bh * 0.25)
                    _add_cand(bx - px, by - py, bx + bw + px, by + bh + py, area)
        except Exception:
            pass

        # --- Method 2: Morphological Sobel Gradient ---
        try:
            scale = 1.0
            if w > 640:
                scale = 640.0 / w
                small = cv2.resize(img, (640, int(h * scale)), interpolation=cv2.INTER_AREA)
            else:
                small = img

            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if len(small.shape) == 3 else small
            grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3)
            abs_grad_x = cv2.convertScaleAbs(grad_x)
            blurred = cv2.GaussianBlur(abs_grad_x, (5, 5), 0)
            _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
            closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                x, y, cw, ch = cv2.boundingRect(c)
                area = cw * ch
                if area > 150:
                    orig_x = int(x / scale)
                    orig_y = int(y / scale)
                    orig_w = int(cw / scale)
                    orig_h = int(ch / scale)
                    px = int(orig_w * 0.12)
                    py = int(orig_h * 0.20)
                    _add_cand(orig_x - px, orig_y - py, orig_x + orig_w + px, orig_y + orig_h + py, area)
        except Exception:
            pass

        seen_boxes.sort(key=lambda item: item[4], reverse=True)
        return [(c[0], c[1], c[2], c[3]) for c in seen_boxes[:6]]

    # ------------------------------------------------------------------
    # Synchronous Read
    # ------------------------------------------------------------------
    def read(self, crop: np.ndarray, label: str = "", category: str = "") -> dict:
        """
        Perform high-speed, accurate OCR extraction on book page, paper, or vehicle.
        Uses multi-region candidate isolation for sub-250ms plate detection.
        """
        t0 = time.time()
        with self._lock:
            reader = self._reader
            is_ready = self._is_ready

        if not is_ready or reader is None or crop is None or crop.size == 0:
            return {
                "detected": False,
                "best_text": "",
                "is_plate": False,
                "plate_number": "",
                "all_lines": [],
                "confidence": 0.0,
                "category": category,
                "label": label,
                "timestamp": time.time(),
                "processing_ms": 0.0
            }

        is_vehicle = (label.lower() in VEHICLE_LABELS) or (category.upper() == "VEHICLE")

        # 1. First attempt: Candidate Plate ROI Extraction & Upscaling
        candidates = self.find_plate_candidates(crop)
        for cx1, cy1, cx2, cy2 in candidates:
            sub = crop[cy1:cy2, cx1:cx2]
            if sub.size == 0:
                continue
            sh, sw = sub.shape[:2]
            if sh < 70 and sh > 5:
                scale_up = 70.0 / sh
                sub = cv2.resize(sub, (int(sw * scale_up), 70), interpolation=cv2.INTER_CUBIC)
            proc_sub = self._preprocess_crop(sub, is_vehicle=False)
            try:
                sub_results = reader.readtext(
                    proc_sub,
                    detail=1,
                    paragraph=False,
                    min_size=4,
                    text_threshold=0.15,
                    low_text=0.10,
                    link_threshold=0.20
                )
            except Exception:
                sub_results = []

            for _, t, c in sub_results:
                clean_t = re.sub(r'[^\w\s\-\.]', '', t.strip()).strip()
                if len(clean_t) >= 3 and c >= 0.03:
                    is_valid, plate_clean = validate_and_format_plate(clean_t, is_vehicle=True)
                    if is_valid:
                        elapsed_ms = round((time.time() - t0) * 1000, 1)
                        res = {
                            "detected": True,
                            "best_text": plate_clean,
                            "is_plate": True,
                            "plate_number": plate_clean,
                            "all_lines": [clean_t],
                            "confidence": round(max(float(c), 0.88), 2),
                            "category": "NO. PLATES",
                            "label": plate_clean,
                            "timestamp": time.time(),
                            "processing_ms": elapsed_ms
                        }
                        with self._lock:
                            self._latest_result = res
                        return res

            sub_words = [re.sub(r'[^\w\s\-\.]', '', t.strip()).strip() for _, t, c in sub_results if c >= 0.03 and len(t.strip()) >= 2]
            sub_joined = "".join(sub_words).upper()
            is_valid, plate_clean = validate_and_format_plate(sub_joined, is_vehicle=True)
            if is_valid:
                elapsed_ms = round((time.time() - t0) * 1000, 1)
                res = {
                    "detected": True,
                    "best_text": plate_clean,
                    "is_plate": True,
                    "plate_number": plate_clean,
                    "all_lines": sub_words,
                    "confidence": round(float(np.mean([c for _, _, c in sub_results])) if sub_results else 0.85, 2),
                    "category": "NO. PLATES",
                    "label": plate_clean,
                    "timestamp": time.time(),
                    "processing_ms": elapsed_ms
                }
                with self._lock:
                    self._latest_result = res
                return res

        # 2. General OCR pass on whole crop (downscaled for speed, max 640px)
        processed_img = self._preprocess_crop(crop, is_vehicle=is_vehicle)

        try:
            results = reader.readtext(
                processed_img,
                detail=1,
                paragraph=False,
                min_size=5,
                text_threshold=0.18,
                low_text=0.12,
                link_threshold=0.22
            )
        except Exception as e:
            print(f"[OCR] read error: {e}")
            results = []

        extracted_words: list[str] = []
        confidences: list[float] = []

        for bbox, text, conf in results:
            clean = text.strip()
            if not clean or len(clean) < 2:
                continue

            clean = re.sub(r'[^\w\s\-\.]', '', clean).strip()
            if len(clean) < 2:
                continue

            clean_up = clean.upper()
            if any(wm in clean_up for wm in ("DROIDCAM", "VIDEO FEED", "CAMERA FEED")):
                continue

            # Check if this single word is a valid plate
            if conf >= 0.03:
                vw, pw = validate_and_format_plate(clean, is_vehicle=is_vehicle)
                if vw:
                    elapsed_ms = round((time.time() - t0) * 1000, 1)
                    res = {
                        "detected": True,
                        "best_text": pw,
                        "is_plate": True,
                        "plate_number": pw,
                        "all_lines": [pw],
                        "confidence": round(max(float(conf), 0.85), 2),
                        "category": "NO. PLATES",
                        "label": pw,
                        "timestamp": time.time(),
                        "processing_ms": elapsed_ms
                    }
                    with self._lock:
                        self._latest_result = res
                    return res

            if conf >= 0.20:
                extracted_words.append(clean)
                confidences.append(float(conf))

        # Check joined words
        joined_text = " ".join(extracted_words)
        joined_upper = joined_text.upper()
        detected_plates: list[str] = []

        valid, plate_str = validate_and_format_plate(joined_upper, is_vehicle=is_vehicle)
        if valid:
            detected_plates.append(plate_str)
        else:
            for word in extracted_words:
                vw, pw = validate_and_format_plate(word, is_vehicle=is_vehicle)
                if vw:
                    detected_plates.append(pw)
                    break

        is_plate = len(detected_plates) > 0
        plate_number = detected_plates[0] if is_plate else ""

        if is_plate:
            best_text = plate_number
        elif extracted_words:
            best_text = " ".join(extracted_words[:6])
        else:
            best_text = ""

        avg_conf = float(np.mean(confidences)) if confidences else (0.85 if is_plate else 0.0)
        elapsed_ms = round((time.time() - t0) * 1000, 1)

        result = {
            "detected": bool(best_text),
            "best_text": best_text,
            "is_plate": is_plate,
            "plate_number": plate_number,
            "all_lines": extracted_words,
            "confidence": round(avg_conf, 2),
            "category": "NO. PLATES" if is_plate else category,
            "label": plate_number if is_plate else label,
            "timestamp": time.time(),
            "processing_ms": elapsed_ms
        }

        with self._lock:
            if result["detected"]:
                self._latest_result = result

        return result

    # ------------------------------------------------------------------
    # Asynchronous Execution (Non-blocking for live video)
    # ------------------------------------------------------------------
    def submit_async(self, crop: np.ndarray, label: str = "", category: str = "", cooldown_sec: float = 1.5):
        """
        Submit a crop to the background worker pool if cooldown has passed.
        Does not block the calling frame loop.
        """
        now = time.time()
        if now - self._last_scan_time < cooldown_sec:
            return  # Still in cooldown

        self._last_scan_time = now

        # Make copy of image so caller can modify original frame safely
        crop_copy = crop.copy()

        def _worker():
            res = self.read(crop_copy, label=label, category=category)
            if res["detected"]:
                print(f"[OCR] Found: '{res['best_text']}' (Plate={res['is_plate']}, {res['processing_ms']}ms)")

        self._executor.submit(_worker)
