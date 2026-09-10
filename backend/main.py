"""
main.py
-------
FastAPI application — AI CCTV Video Analytics backend.

Endpoints:
  POST   /api/source          — set video source (webcam or URL)
  DELETE /api/source          — stop current stream
  GET    /api/stream          — MJPEG stream of processed frames
  POST   /api/boundary        — set virtual boundary polygon
  DELETE /api/boundary        — clear boundary
  GET    /api/alerts          — get all alerts (JSON)
  DELETE /api/alerts          — clear alerts
  WS     /ws                  — push {summary, alerts, active_intrusion} per frame
"""

import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

import asyncio
import json
import threading
import time
import cv2
import numpy as np
from collections import defaultdict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from video_stream    import VideoStream
from detector        import Detector
from boundary        import BoundaryManager
from alerts          import AlertManager
from detection_log   import DetectionLog
from ocr_reader      import OCRReader
from email_notifier  import EmailNotifier

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="AI CCTV Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Shared singletons
# ---------------------------------------------------------------------------

stream         = VideoStream()
detector       = Detector()
boundary       = BoundaryManager()
alert_mgr      = AlertManager()
detect_log     = DetectionLog()
ocr_reader     = OCRReader()
email_notifier = EmailNotifier()

# Latest processed data (updated by the processing thread)
_state_lock = threading.Lock()
_latest: dict = {
    "detections":        [],
    "summary":           {},           # {category: {label: count}} — built from YOLO output
    "intruding_indices": set(),
    "dwell_times":       {},
    "active_intrusion":  False,
    "camera_blocked":    False,
    "ocr":               {},
    "email_status":      email_notifier.get_status(),
    "error":             None,
}

# Camera occlusion / blockage tracker
_occlusion_counter = 0
_camera_blocked_state = False
_last_blocked_alert_time = 0.0

# Number plate log deduplication tracker
_last_logged_plate = ""
_last_logged_plate_time = 0.0

# WebSocket clients
_ws_clients: set[WebSocket] = set()
_ws_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# Processing thread
# ---------------------------------------------------------------------------

PROCESS_EVERY_N = 2   # run YOLO on every Nth frame for performance
_frame_counter  = 0


def processing_loop():
    global _frame_counter, _occlusion_counter, _camera_blocked_state, _last_blocked_alert_time
    global _last_logged_plate, _last_logged_plate_time
    while True:
        time.sleep(0.02)   # ~50 fps ceiling

        if not stream.is_running:
            with _state_lock:
                _latest["error"] = stream.error
                _latest["camera_blocked"] = False
                _latest["ocr"] = {"detected": False}
                _latest["detections"] = []
                _latest["active_intrusion"] = False
            _camera_blocked_state = False
            _occlusion_counter = 0
            continue

        frame = stream.get_frame()
        if frame is None:
            continue

        _frame_counter += 1
        if _frame_counter % PROCESS_EVERY_N != 0:
            continue

        h, w = frame.shape[:2]
        boundary.update_frame_size(w, h)

        # --- Camera occlusion / blockage check ---
        # When lens is covered by hand or object: average brightness is very low
        # Or image is completely flat/blurred with near-zero contrast/variance
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_b = float(np.mean(gray))
        std_b = float(np.std(gray))
        lap_v = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        # Occluded if dark (<28.0) or flat/featureless (<7.0 std and <18.0 laplacian)
        is_occluded = (mean_b < 28.0) or (std_b < 7.0 and lap_v < 18.0) or (mean_b < 40.0 and std_b < 9.0)

        if is_occluded:
            _occlusion_counter += 1
        else:
            _occlusion_counter = max(0, _occlusion_counter - 1)

        is_blocked = (_occlusion_counter >= 2)

        if is_blocked:
            if not _camera_blocked_state:
                _camera_blocked_state = True
                alert_mgr.add_custom_alert(
                    title="CAMERA OCCLUSION DETECTED",
                    message="CRITICAL: Camera lens covered or visual feed obstructed!",
                    category="TAMPER",
                    emoji="🚨"
                )
                detect_log.add_custom_entry(
                    label="CAMERA OCCLUSION",
                    category="TAMPER",
                    confidence=1.0,
                    intruding=True,
                    emoji="🚨"
                )
                _last_blocked_alert_time = time.time()
            else:
                if time.time() - _last_blocked_alert_time > 10.0:
                    alert_mgr.add_custom_alert(
                        title="CAMERA STILL BLOCKED",
                        message="Ongoing camera feed occlusion detected!",
                        category="TAMPER",
                        emoji="🚨"
                    )
                    _last_blocked_alert_time = time.time()
        else:
            if _camera_blocked_state:
                _camera_blocked_state = False
                alert_mgr.add_custom_alert(
                    title="CAMERA RESTORED",
                    message="Visual feed restored — surveillance active",
                    category="SYSTEM",
                    emoji="✅"
                )
                detect_log.add_custom_entry(
                    label="CAMERA RESTORED",
                    category="SYSTEM",
                    confidence=1.0,
                    intruding=False,
                    emoji="✅"
                )

        # --- YOLO detection ---
        detections = detector.detect(frame)

        # --- Boundary check (inside OR touching edge) ---
        intruding = set()
        if boundary.is_active():
            for i, det in enumerate(detections):
                if boundary.is_inside_or_touching(det["ref_point"]):
                    intruding.add(i)

        # --- OCR & ANPR: Scan vehicles and foreground items asynchronously ---
        latest_ocr = ocr_reader.get_latest()
        for i, det in enumerate(detections):
            is_veh = (det["category"] == "VEHICLE") or (det["label"] in {"car", "motorcycle", "bus", "truck", "van", "auto", "license plate", "number plate"})
            is_phone = (det["label"] in {"cell phone", "laptop"})
            # Automatically scan verified vehicles, license plates, phones, or high-dwell intruders
            is_target = is_veh or is_phone or (i in intruding and dwell_times.get(det.get("track_id", 0), 0) >= 4.0)

            if is_target:
                x1, y1, x2, y2 = det["bbox"]
                x1, y1 = max(0, int(x1)), max(0, int(y1))
                x2, y2 = min(w, int(x2)), min(h, int(y2))
                if (x2 - x1) > 40 and (y2 - y1) > 20:
                    ocr_reader.submit_async(frame[y1:y2, x1:x2], label=det["label"], category=det["category"], cooldown_sec=1.5)

            # If recent OCR matches or is fresh within 3.5s, enrich this detection
            if latest_ocr.get("detected") and (time.time() - latest_ocr.get("timestamp", 0) < 3.5):
                if (det["label"] == latest_ocr.get("label")) or (det["category"] == latest_ocr.get("category")) or is_veh or is_phone or (i in intruding):
                    det["ocr_text"] = latest_ocr.get("best_text", "")
                    det["is_plate"] = latest_ocr.get("is_plate", False)
                    det["plate_number"] = latest_ocr.get("plate_number", "")

        # Automatically log confirmed number plates under "NO. PLATES" category
        if latest_ocr.get("is_plate") and latest_ocr.get("plate_number"):
            p_num = latest_ocr.get("plate_number")
            if (p_num != _last_logged_plate) or (time.time() - _last_logged_plate_time > 10.0):
                detect_log.add_custom_entry(
                    label=p_num,
                    category="NO. PLATES",
                    confidence=latest_ocr.get("confidence", 0.95),
                    intruding=False,
                    emoji="🚘"
                )
                _last_logged_plate = p_num
                _last_logged_plate_time = time.time()

        # --- Alert management (5-second dwell timer) ---
        new_alerts = alert_mgr.process(detections, intruding)
        dwell_times = alert_mgr.get_dwell_times(detections, intruding)

        # Dispatch automated email alert with annotated snapshot if breach fired
        if new_alerts:
            for alt in new_alerts:
                print(f"[MAIN] [ALERT] INTRUSION FIRED: {alt.get('message', 'Boundary breached')}")
                try:
                    email_notifier.send_intrusion_alert_async(alt, frame, boundary.get_points())
                except Exception as e:
                    print(f"[MAIN] [ERROR] Email dispatch trigger failed: {e}")

        # --- Detection log (every detected object, deduplicated) ---
        detect_log.update(detections, intruding)

        # --- Summary: two-level {category → {yolo_label → count}} ---
        summary: dict[str, dict[str, int]] = {}
        for det in detections:
            cat = det["category"]           # e.g. "VEHICLE" (from JSON)
            lbl = det["label"]              # e.g. "car"    (from YOLO)
            if cat not in summary:
                summary[cat] = {}
            summary[cat][lbl] = summary[cat].get(lbl, 0) + 1

        if latest_ocr.get("is_plate") and latest_ocr.get("plate_number") and (time.time() - latest_ocr.get("timestamp", 0) < 6.0):
            if "NO. PLATES" not in summary:
                summary["NO. PLATES"] = {}
            summary["NO. PLATES"][latest_ocr.get("plate_number")] = 1

        # Broadcast OCR data if fresh (< 4.5s), otherwise clear so client HUD naturally dismisses
        is_fresh_ocr = latest_ocr.get("detected") and (time.time() - latest_ocr.get("timestamp", 0) < 4.5)
        ocr_broadcast = latest_ocr if is_fresh_ocr else {"detected": False}

        with _state_lock:
            _latest["detections"]        = detections
            _latest["summary"]           = summary
            _latest["intruding_indices"] = intruding
            _latest["dwell_times"]       = dwell_times
            _latest["camera_blocked"]    = _camera_blocked_state
            _latest["active_intrusion"]  = (len(intruding) > 0) or _camera_blocked_state
            _latest["ocr"]               = ocr_broadcast
            _latest["email_status"]      = email_notifier.get_status()
            _latest["error"]             = stream.error


_proc_thread = threading.Thread(target=processing_loop, daemon=True)
_proc_thread.start()


# ---------------------------------------------------------------------------
# MJPEG stream generator
# ---------------------------------------------------------------------------

def mjpeg_generator():
    """Yield processed frames as multipart JPEG."""
    while True:
        time.sleep(0.033)   # ~30 fps

        if not stream.is_running:
            # Send a black "no signal" frame
            blank = np.zeros((480, 640, 3), dtype=np.uint8)
            msg = stream.error or "No stream active"
            cv2.putText(
                blank, msg,
                (30, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (0, 60, 200), 2, cv2.LINE_AA,
            )
            ret, buf = cv2.imencode(".jpg", blank)
            if ret:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + buf.tobytes()
                    + b"\r\n"
                )
            continue

        frame = stream.get_frame()
        if frame is None:
            continue

        # Draw boundary (flash when actively intruding)
        with _state_lock:
            alert_on = _latest["active_intrusion"]
            is_cam_blocked = _latest.get("camera_blocked", False)
        frame = boundary.draw(frame, alert_active=alert_on)

        # Draw detections
        with _state_lock:
            dets      = _latest["detections"]
            intruding = _latest["intruding_indices"]

        frame = detector.draw(frame, dets, intruding)

        # Flash red border on intrusion or camera occlusion
        if intruding or is_cam_blocked:
            h, w = frame.shape[:2]
            cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 6)

        if is_cam_blocked:
            h, w = frame.shape[:2]
            overlay = frame.copy()
            cv2.rectangle(overlay, (20, h // 2 - 40), (w - 20, h // 2 + 40), (10, 10, 20), -1)
            cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
            cv2.putText(
                frame, "WARNING: CAMERA BLOCKED / OCCLUDED",
                (max(25, w // 2 - 250), h // 2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.72,
                (0, 0, 255), 2, cv2.LINE_AA,
            )
            cv2.putText(
                frame, "Lens covered - Tamper event logged in Alerts tab",
                (max(25, w // 2 - 230), h // 2 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                (0, 215, 255), 1, cv2.LINE_AA,
            )

        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ret:
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                + buf.tobytes()
                + b"\r\n"
            )


# ---------------------------------------------------------------------------
# WebSocket broadcaster
# ---------------------------------------------------------------------------

async def broadcast_loop():
    """Send detection state to all WS clients every 200 ms."""
    while True:
        await asyncio.sleep(0.2)
        if not _ws_clients:
            continue

        with _state_lock:
            summary        = _latest["summary"]
            intrusion      = _latest["active_intrusion"]
            camera_blocked = _latest.get("camera_blocked", False)
            ocr_data       = _latest.get("ocr", {})
            error          = _latest["error"]

        recent_alerts = alert_mgr.get_all()[:20]
        recent_log    = detect_log.get_all()[:60]

        with _state_lock:
            dwell_times  = _latest.get("dwell_times", {})
            email_status = _latest.get("email_status", {})

        # Convert set keys to strings for JSON serialisation
        dwell_serialisable = {str(k): round(v, 1) for k, v in dwell_times.items()}

        payload = {
            "summary":          summary,
            "active_intrusion": intrusion,
            "camera_blocked":   camera_blocked,
            "alerts":           recent_alerts,
            "dwell_times":      dwell_serialisable,
            "detection_log":    recent_log,
            "detection_mode":   detector.mode,
            "ocr":              ocr_data,
            "email_status":     email_status,
            "error":            error,
        }

        dead = set()
        async with _ws_lock:
            for ws in _ws_clients:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.add(ws)
            _ws_clients.difference_update(dead)


@app.on_event("startup")
async def startup():
    asyncio.create_task(broadcast_loop())


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "SIHCCTV Analytics",
        "active_stream": stream.is_running,
        "mode": detector.mode
    }


class SourceRequest(BaseModel):
    type: str          # "webcam" | "url"
    url:  str = ""


@app.post("/api/source")
async def set_source(req: SourceRequest):
    if req.type == "webcam":
        ok = stream.start(0)
    elif req.type == "url":
        if not req.url:
            return JSONResponse({"ok": False, "error": "URL is required"}, status_code=400)
        ok = stream.start(req.url)
    else:
        return JSONResponse({"ok": False, "error": "Unknown source type"}, status_code=400)

    if not ok:
        return JSONResponse({"ok": False, "error": stream.error}, status_code=400)

    alert_mgr.clear()
    detect_log.clear()
    boundary.clear()
    return {"ok": True}


@app.delete("/api/source")
async def stop_source():
    stream.stop()
    alert_mgr.clear()
    detect_log.clear()
    return {"ok": True}


@app.get("/api/stream")
async def video_stream():
    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


class BoundaryRequest(BaseModel):
    points: list[list[float]]   # [[x,y], ...] normalised 0..1


@app.post("/api/boundary")
async def set_boundary(req: BoundaryRequest):
    if len(req.points) < 3:
        return JSONResponse({"ok": False, "error": "Need at least 3 points"}, status_code=400)
    boundary.set_boundary(req.points)
    return {"ok": True, "points": len(req.points)}


@app.delete("/api/boundary")
async def clear_boundary():
    boundary.clear()
    return {"ok": True}


@app.get("/api/alerts")
async def get_alerts():
    return {"alerts": alert_mgr.get_all()}


@app.delete("/api/alerts")
async def clear_alerts():
    alert_mgr.clear()
    return {"ok": True}


@app.get("/api/detection-log")
async def get_detection_log():
    """Return the full rolling detection log (newest first)."""
    return {"log": detect_log.get_all()}


@app.delete("/api/detection-log")
async def clear_detection_log():
    detect_log.clear()
    return {"ok": True}


@app.delete("/api/logs")
async def clear_all_logs():
    """Clear both incident alerts and detection logs simultaneously."""
    alert_mgr.clear()
    detect_log.clear()
    with _state_lock:
        _latest["active_intrusion"] = False
    return {"ok": True}


class ModeRequest(BaseModel):
    mode: str  # "all" | "person_wearables"


@app.post("/api/detection-mode")
async def set_detection_mode(req: ModeRequest):
    if req.mode not in ("all", "person_wearables"):
        return JSONResponse({"ok": False, "error": "Invalid mode"}, status_code=400)
    current = detector.set_mode(req.mode)
    return {"ok": True, "mode": current}


@app.get("/api/detection-mode")
async def get_detection_mode():
    return {"mode": detector.mode}


# ---------------------------------------------------------------------------
# OCR & ANPR Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/ocr/scan")
def trigger_ocr_scan():
    """Immediately capture current frame and run OCR/ANPR text extraction."""
    if not stream.is_running:
        return JSONResponse({"ok": False, "error": "No stream active"}, status_code=400)

    frame = stream.get_frame()
    if frame is None:
        return JSONResponse({"ok": False, "error": "No frame available from video stream"}, status_code=400)

    global _last_logged_plate, _last_logged_plate_time

    h, w = frame.shape[:2]
    # Crop out top 8% of frame to eliminate DroidCam watermark / timestamp overlay
    clean_frame = frame[int(h * 0.08):, :]

    # Prioritize vehicle, license plate, cell phone, book, or foreground objects
    target_crop = clean_frame
    best_label = ""
    best_cat = ""
    with _state_lock:
        dets = _latest.get("detections", [])
        candidates = [
            d for d in dets
            if d["category"] == "VEHICLE"
            or d["label"] in {"car", "license plate", "number plate", "motorcycle", "bus", "truck", "book", "cell phone"}
        ]
        if not candidates and dets:
            candidates = [d for d in dets if d["category"] != "HUMAN"]
        if candidates:
            best_det = max(candidates, key=lambda d: (d["bbox"][2] - d["bbox"][0]) * (d["bbox"][3] - d["bbox"][1]))
            x1, y1, x2, y2 = best_det["bbox"]
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(w, int(x2)), min(h, int(y2))
            if (x2 - x1) > 40 and (y2 - y1) > 20:
                target_crop = frame[y1:y2, x1:x2]
                best_label = best_det.get("label", "")
                best_cat = best_det.get("category", "")

    # 1. First attempt: scan the target crop (detected vehicle/phone/plate)
    res = ocr_reader.read(target_crop, label=best_label, category=best_cat)

    # 2. Second attempt: center 75% viewport (where users hold up cards, phones, documents)
    if not res.get("detected"):
        center_crop = clean_frame[int(h * 0.12):int(h * 0.88), int(w * 0.12):int(w * 0.88)]
        if center_crop.size > 0:
            res_center = ocr_reader.read(center_crop)
            if res_center.get("detected"):
                res = res_center

    # 3. Third attempt: full clean frame
    if not res.get("detected") and target_crop is not clean_frame:
        res = ocr_reader.read(clean_frame)

    if res.get("detected"):
        with _state_lock:
            _latest["ocr"] = res
            for det in _latest.get("detections", []):
                det["ocr_text"] = res.get("best_text", "")
                det["is_plate"] = res.get("is_plate", False)
                det["plate_number"] = res.get("plate_number", "")

        # Immediately log confirmed plate under "NO. PLATES" category
        if res.get("is_plate") and res.get("plate_number"):
            p_num = res["plate_number"]
            detect_log.add_custom_entry(
                label=p_num,
                category="NO. PLATES",
                confidence=res.get("confidence", 0.95),
                intruding=False,
                emoji="🚘"
            )
            _last_logged_plate = p_num
            _last_logged_plate_time = time.time()
    return {"ok": True, "result": res}


@app.get("/api/ocr/latest")
def get_latest_ocr():
    return {"ok": True, "ocr": ocr_reader.get_latest()}


# ---------------------------------------------------------------------------
# Notification Configuration & Test Dispatch Endpoints
# ---------------------------------------------------------------------------

class NotificationConfigModel(BaseModel):
    enabled: bool = False
    recipient_email: str = ""
    sender_email: str = ""
    app_password: str = ""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    cooldown_sec: int = 45


@app.get("/api/notifications/config")
def get_notification_config():
    return {"ok": True, "config": email_notifier.get_status()}


@app.post("/api/notifications/config")
def update_notification_config(body: NotificationConfigModel):
    success = email_notifier.save_config(body.dict())
    with _state_lock:
        _latest["email_status"] = email_notifier.get_status()
    return {"ok": success, "config": email_notifier.get_status()}


class TestEmailModel(BaseModel):
    recipient_email: str = ""


@app.post("/api/notifications/test")
def trigger_test_email(body: TestEmailModel):
    frame = stream.get_frame()
    recipient = body.recipient_email or email_notifier.config.get("recipient_email")
    if not recipient:
        return JSONResponse({"ok": False, "error": "No recipient email provided"}, status_code=400)

    test_alert = {
        "title": "CCTV LIVE OPTICAL SNAPSHOT / TEST BEACON",
        "message": "Live camera snapshot captured from CCTV dashboard",
        "category": "SYSTEM",
        "label": "LIVE_FEED",
        "time": time.strftime("%H:%M:%S"),
        "confidence": 1.0,
    }
    with _state_lock:
        dets = _latest.get("detections", [])
        if dets:
            test_alert["bbox"] = dets[0].get("bbox")
            test_alert["label"] = dets[0].get("label")
            test_alert["category"] = dets[0].get("category")

    ok, msg = email_notifier.send_test_email(
        recipient,
        test_frame=frame,
        boundary_points=boundary.get_points(),
        custom_alert=test_alert
    )
    with _state_lock:
        _latest["email_status"] = email_notifier.get_status()
    if not ok:
        return JSONResponse({"ok": False, "error": msg}, status_code=500)
    return {"ok": True, "message": msg}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    async with _ws_lock:
        _ws_clients.add(ws)
    try:
        while True:
            text = await ws.receive_text()
            try:
                msg = json.loads(text)
                cmd = msg.get("action")
                if cmd in ("clear_all", "clear_logs"):
                    alert_mgr.clear()
                    detect_log.clear()
                    with _state_lock:
                        _latest["active_intrusion"] = False
                    await ws.send_json({
                        "alerts": [],
                        "detection_log": [],
                        "active_intrusion": False,
                        "dwell_times": {},
                    })
                elif cmd == "clear_alerts":
                    alert_mgr.clear()
                    await ws.send_json({"alerts": []})
                elif cmd == "clear_detection_log":
                    detect_log.clear()
                    await ws.send_json({"detection_log": []})
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        async with _ws_lock:
            _ws_clients.discard(ws)
