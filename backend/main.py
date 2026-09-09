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

import asyncio
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

stream      = VideoStream()
detector    = Detector()
boundary    = BoundaryManager()
alert_mgr   = AlertManager()
detect_log  = DetectionLog()

# Latest processed data (updated by the processing thread)
_state_lock = threading.Lock()
_latest: dict = {
    "detections":        [],
    "summary":           {},           # {category: {label: count}} — built from YOLO output
    "intruding_indices": set(),
    "dwell_times":       {},
    "active_intrusion":  False,
    "error":             None,
}

# WebSocket clients
_ws_clients: set[WebSocket] = set()
_ws_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# Processing thread
# ---------------------------------------------------------------------------

PROCESS_EVERY_N = 2   # run YOLO on every Nth frame for performance
_frame_counter  = 0


def processing_loop():
    global _frame_counter
    while True:
        time.sleep(0.02)   # ~50 fps ceiling

        if not stream.is_running:
            with _state_lock:
                _latest["error"] = stream.error
            continue

        frame = stream.get_frame()
        if frame is None:
            continue

        _frame_counter += 1
        if _frame_counter % PROCESS_EVERY_N != 0:
            continue

        h, w = frame.shape[:2]
        boundary.update_frame_size(w, h)

        # --- YOLO detection ---
        detections = detector.detect(frame)

        # --- Boundary check (inside OR touching edge) ---
        intruding = set()
        if boundary.is_active():
            for i, det in enumerate(detections):
                if boundary.is_inside_or_touching(det["ref_point"]):
                    intruding.add(i)

        # --- Alert management (5-second dwell timer) ---
        alert_mgr.process(detections, intruding)
        dwell_times = alert_mgr.get_dwell_times(detections, intruding)

        # --- Detection log (every detected object, deduplicated) ---
        detect_log.update(detections, intruding)

        # --- Summary: two-level {category → {yolo_label → count}} ---
        # category comes from coco_classes.json lookup (no Python hardcode)
        # label is the raw YOLO class name (bottle, car, dog, person, ...)
        summary: dict[str, dict[str, int]] = {}
        for det in detections:
            cat = det["category"]           # e.g. "VEHICLE" (from JSON)
            lbl = det["label"]              # e.g. "car"    (from YOLO)
            if cat not in summary:
                summary[cat] = {}
            summary[cat][lbl] = summary[cat].get(lbl, 0) + 1

        with _state_lock:
            _latest["detections"]        = detections
            _latest["summary"]           = summary
            _latest["intruding_indices"] = intruding
            _latest["dwell_times"]       = dwell_times
            _latest["active_intrusion"]  = len(intruding) > 0
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
        frame = boundary.draw(frame, alert_active=alert_on)

        # Draw detections
        with _state_lock:
            dets     = _latest["detections"]
            intruding = _latest["intruding_indices"]

        frame = detector.draw(frame, dets, intruding)

        # Flash red border on intrusion
        if intruding:
            h, w = frame.shape[:2]
            cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 6)

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
            summary   = _latest["summary"]
            intrusion = _latest["active_intrusion"]
            error     = _latest["error"]

        recent_alerts = alert_mgr.get_all()[:10]
        recent_log    = detect_log.get_all()[:50]

        with _state_lock:
            dwell_times = _latest.get("dwell_times", {})

        # Convert set keys to strings for JSON serialisation
        dwell_serialisable = {str(k): round(v, 1) for k, v in dwell_times.items()}

        payload = {
            "summary":          summary,
            "active_intrusion": intrusion,
            "alerts":           recent_alerts,
            "dwell_times":      dwell_serialisable,
            "detection_log":    recent_log,
            "detection_mode":   detector.mode,
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
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    async with _ws_lock:
        _ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()   # keep alive
    except WebSocketDisconnect:
        pass
    finally:
        async with _ws_lock:
            _ws_clients.discard(ws)
