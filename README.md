# AI CCTV — Video Analytics Prototype
### Smart India Hackathon

> Intelligent security surveillance: real-time YOLO object detection, virtual boundary drawing, and intrusion alerting.

--------------------------------------------------
# DEMO PHASE SCREENSHOT 
<img width="1917" height="872" alt="image" src="https://github.com/user-attachments/assets/ec33b37d-5802-42f8-9927-ad0f51387ecb" />

--------------------------------------------------------

## Architecture

```
React (Vite, port 5173)
  │
  ├── GET  http://localhost:8000/api/stream   ← MJPEG video (drawn in <img>)
  └── WS   ws://localhost:8000/ws             ← JSON {summary, alerts, active_intrusion}
                  │
           FastAPI (port 8000)
                  │
        ┌─────────┴─────────┐
        │                   │
   VideoStream          YOLO11n / YOLOv8n
   (cv2.VideoCapture)   (Ultralytics)
        │
   BoundaryManager + AlertManager
```

---

## Quick Start

### 1. Backend

```bash
cd backend

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

> YOLO model (`yolo11n.pt` or `yolov8n.pt`) will be auto-downloaded (~6 MB) on first run.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open: **http://localhost:5173**

---

## Usage

### Webcam
1. Click **📷 Laptop Webcam**
2. Click **▶ Connect**
3. Live video with YOLO boxes appears immediately

### Phone Camera Stream
1. Install any MJPEG/IP camera app on your Android phone:
   - **DroidCam** — free, reliable
   - **IP Webcam** — popular, feature-rich
   - **EpocCam**
2. Connect phone and laptop to the **same Wi-Fi network**
3. Note the stream URL shown in the app (e.g., `http://192.168.1.10:8080/video`)
4. In the dashboard: click **📡 Stream URL**
5. Enter the URL → click **▶ Connect**

RTSP streams also work:
```
rtsp://192.168.1.10:8554/stream
```

### Drawing a Boundary
1. With video running, click **✏ Draw Boundary**
2. **Click on the video** to add polygon points (minimum 3)
   - Example: click 4 corners of the right-half of the screen
3. Click **✓ Finish** to send the boundary to the backend
4. The red zone appears overlaid on the live video
5. Walk into the zone → 🚨 alert fires in the sidebar

### Clearing
- **✕ Clear Boundary** — removes the polygon
- **Clear** button in alerts panel — clears the alert log

---

## Features

| Feature | Detail |
|---|---|
| Video sources | Webcam (index 0), HTTP/MJPEG URL, RTSP URL |
| YOLO model | yolo11n.pt (6 MB, COCO 80 classes) |
| Categories | HUMAN / ANIMAL / VEHICLE / OBJECT |
| Bounding box | Label + confidence score drawn on every detection |
| Virtual boundary | User-drawn polygon, visible as red semi-transparent overlay |
| Intrusion detection | Bottom-centre of bbox tested with `cv2.pointPolygonTest` |
| Alert cooldown | 5-second cooldown + entry-only triggering (no flood) |
| Video streaming | MJPEG via `multipart/x-mixed-replace` (zero JS overhead) |
| Coordinates | Normalised [0..1] from frontend → scaled to frame pixels in backend |

---

## Troubleshooting

### Backend won't start
```
pip install --upgrade pip
pip install -r requirements.txt
```
If `ultralytics` install fails: `pip install ultralytics --no-cache-dir`

### Webcam not found
- Check another app isn't using the webcam
- Try changing `VideoCapture(0)` to `VideoCapture(1)` in `video_stream.py`

### Stream URL doesn't connect
- Make sure phone and laptop are on the **same Wi-Fi** (not mobile data)
- Test the URL in your browser first — it should show video or an MJPEG page
- If it's an RTSP stream, OpenCV needs `ffmpeg` support:
  ```bash
  pip install opencv-python-headless  # headless variant often has better codec support
  ```

### Video shows but YOLO boxes are wrong / boundary misaligned
- This would be a coordinate bug — please open an issue with your frame resolution
- You can check actual frame size in the backend logs on startup

### CORS error in browser
- Make sure FastAPI is running on port **8000** (not 8001 or another port)
- If you changed the port, update `API` and `WS_URL` constants in `frontend/src/App.jsx`

### Port 8000 already in use
```bash
uvicorn main:app --reload --port 8001
```
Then update `App.jsx`:
```js
const API    = 'http://localhost:8001';
const WS_URL = 'ws://localhost:8001/ws';
```

---

## Project Structure

```
SIHCCTV/
├── backend/
│   ├── main.py          ← FastAPI app, MJPEG stream, WebSocket
│   ├── video_stream.py  ← Threaded VideoCapture (webcam/HTTP/RTSP)
│   ├── detector.py      ← YOLO detection + category mapping
│   ├── boundary.py      ← Polygon management + point-in-polygon
│   ├── alerts.py        ← Alert cooldown + log management
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── index.css
│   │   └── components/
│   │       ├── VideoSourceSelector.jsx
│   │       ├── VideoDisplay.jsx       ← MJPEG img + canvas overlay
│   │       ├── BoundaryControls.jsx
│   │       ├── DetectionSummary.jsx
│   │       └── AlertPanel.jsx
│   ├── package.json
│   └── vite.config.js
│
└── README.md
```

---

## Future Additions (not implemented — modular architecture ready)

- ByteTrack person tracking + Re-ID
- ANPR (license plate recognition)
- Night-time / low-light mode
- Multi-camera support
- Suspicious activity detection
- Event database (PostgreSQL / SQLite)
- Command & control integration
# SIHCCTV
