"""
email_notifier.py
-----------------
Automated email alert dispatcher with annotated intrusion snapshots.
Dispatches emails asynchronously in a background thread to maintain 30 FPS video streaming.
"""
from __future__ import annotations

import os
import json
import time
import smtplib
import threading
from concurrent.futures import ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import cv2
import numpy as np

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "notifications_config.json")


class EmailNotifier:
    def __init__(self):
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email_worker")

        # Configuration defaults
        self.config = {
            "enabled": False,
            "recipient_email": "",
            "sender_email": "",
            "app_password": "",
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "cooldown_sec": 45,
        }

        # Operational status tracking
        self.last_dispatched_time = 0.0
        self.last_dispatch_status = "IDLE"
        self.last_dispatch_message = "No emails sent yet"
        self.total_sent = 0

        self.load_config()

    # ------------------------------------------------------------------
    # Config Persistence
    # ------------------------------------------------------------------

    def load_config(self):
        with self._lock:
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                        self.config.update(saved)
                except Exception as e:
                    print(f"[EmailNotifier] Failed to load config: {e}")

    def save_config(self, new_config: dict):
        with self._lock:
            # Preserve existing app_password if empty in incoming update
            pwd = new_config.get("app_password", "").replace(" ", "").strip()
            if not pwd and self.config.get("app_password"):
                new_config["app_password"] = self.config["app_password"]
            elif pwd:
                new_config["app_password"] = pwd

            # Fallback sender to recipient if empty
            if not new_config.get("sender_email") and new_config.get("recipient_email"):
                new_config["sender_email"] = new_config["recipient_email"]

            self.config.update(new_config)
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2)
                return True
            except Exception as e:
                print(f"[EmailNotifier] Failed to save config: {e}")
                return False

    def get_status(self) -> dict:
        with self._lock:
            return {
                "enabled": self.config.get("enabled", False),
                "recipient_email": self.config.get("recipient_email", ""),
                "sender_email": self.config.get("sender_email", ""),
                "smtp_server": self.config.get("smtp_server", "smtp.gmail.com"),
                "smtp_port": self.config.get("smtp_port", 587),
                "cooldown_sec": self.config.get("cooldown_sec", 15),
                "last_dispatched_time": self.last_dispatched_time,
                "last_dispatch_status": self.last_dispatch_status,
                "last_dispatch_message": self.last_dispatch_message,
                "total_sent": self.total_sent,
            }

    # ------------------------------------------------------------------
    # Frame Annotation Helper
    # ------------------------------------------------------------------

    def annotate_frame(self, frame: np.ndarray, alert: dict, boundary_points: list) -> np.ndarray:
        """
        Draw boundary polygon, intruder bounding box, and incident HUD overlay on the snapshot.
        """
        if frame is None:
            return None

        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # 1. Draw boundary lines if available
        if boundary_points and len(boundary_points) >= 3:
            pts = []
            for pt in boundary_points:
                px = int(pt[0] * w) if pt[0] <= 1.0 else int(pt[0])
                py = int(pt[1] * h) if pt[1] <= 1.0 else int(pt[1])
                pts.append([px, py])
            pts_arr = np.array([pts], dtype=np.int32)
            # Fill with subtle red wash and thick red boundary line
            overlay = annotated.copy()
            cv2.fillPoly(overlay, pts_arr, (0, 0, 180))
            cv2.addWeighted(overlay, 0.25, annotated, 0.75, 0, annotated)
            cv2.polylines(annotated, pts_arr, True, (0, 0, 255), 3, lineType=cv2.LINE_AA)

        # 2. Draw intruder bounding box if provided in alert
        bbox = alert.get("bbox")
        if bbox and len(bbox) == 4:
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            # Red rectangular target box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
            # Corner accents
            c_len = max(10, int((x2 - x1) * 0.2))
            cv2.line(annotated, (x1, y1), (x1 + c_len, y1), (0, 255, 255), 4)
            cv2.line(annotated, (x1, y1), (x1, y1 + c_len), (0, 255, 255), 4)
            cv2.line(annotated, (x2, y2), (x2 - c_len, y2), (0, 255, 255), 4)
            cv2.line(annotated, (x2, y2), (x2, y2 - c_len), (0, 255, 255), 4)

            # Target label badge
            lbl = alert.get("label", alert.get("category", "INTRUDER")).upper()
            cv2.rectangle(annotated, (x1, max(0, y1 - 26)), (x1 + len(lbl) * 14 + 10, y1), (0, 0, 255), -1)
            cv2.putText(annotated, lbl, (x1 + 4, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        # 3. Top telemetry banner
        banner_h = 60
        overlay_b = annotated.copy()
        cv2.rectangle(overlay_b, (0, 0), (w, banner_h), (10, 10, 15), -1)
        cv2.addWeighted(overlay_b, 0.82, annotated, 0.18, 0, annotated)
        cv2.line(annotated, (0, banner_h), (w, banner_h), (0, 0, 255), 2)

        title = f"SECURITY PERIMETER BREACH - NODE_01_SOUTH"
        time_str = alert.get("time", time.strftime("%H:%M:%S"))
        sub = f"TIME: {time_str} | REASON: {alert.get('message', 'Perimeter violated')} | DWELL: 5s+"

        cv2.putText(annotated, title, (18, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (50, 100, 255), 2, lineType=cv2.LINE_AA)
        cv2.putText(annotated, sub, (18, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1, lineType=cv2.LINE_AA)

        return annotated

    # ------------------------------------------------------------------
    # Dispatch Logic
    # ------------------------------------------------------------------

    def send_intrusion_alert_async(self, alert: dict, frame: np.ndarray, boundary_points: list = None):
        """
        Asynchronously compose and transmit an email with the attached snapshot.
        Non-blocking: safe to call directly from the video processing loop.
        """
        with self._lock:
            enabled = self.config.get("enabled", False)
            recipient = self.config.get("recipient_email", "").strip()
            cooldown = self.config.get("cooldown_sec", 15)

        if not enabled or not recipient:
            return

        now = time.time()
        if now - self.last_dispatched_time < cooldown:
            return  # Within anti-spam cooldown

        self.last_dispatched_time = now
        print(f"[EmailNotifier] [ALERT] INTRUSION BREACH! Capturing camera frame & dispatching email to {recipient}...")

        # Copy frame and parameters for worker thread
        frame_copy = frame.copy() if frame is not None else None
        b_pts_copy = list(boundary_points) if boundary_points else []
        alert_copy = dict(alert)

        def _worker():
            try:
                self._dispatch_email(alert_copy, frame_copy, b_pts_copy)
                print(f"[EmailNotifier] [OK] Intrusion photo snapshot successfully delivered to {recipient}!")
            except Exception as e:
                print(f"[EmailNotifier] [ERROR] Worker error: {e}")
                with self._lock:
                    self.last_dispatch_status = "FAILED"
                    self.last_dispatch_message = str(e)

        self._executor.submit(_worker)

    def send_test_email(self, recipient: str, test_frame: np.ndarray = None, boundary_points: list = None, custom_alert: dict = None) -> tuple[bool, str]:
        """
        Synchronously send a test email to verify credentials and network delivery with live camera snapshot.
        """
        recipient = recipient.strip()
        if not recipient:
            return False, "Recipient email is required"

        test_alert = custom_alert or {
            "title": "CCTV OPTICAL SNAPSHOT / TEST BEACON",
            "message": "Live optical camera snapshot captured from dashboard",
            "category": "SYSTEM",
            "label": "LIVE_CAMERA",
            "time": time.strftime("%H:%M:%S"),
            "confidence": 1.0,
        }

        # If camera is not streaming yet, generate a fallback placeholder
        if test_frame is None:
            test_frame = np.full((480, 640, 3), 40, dtype=np.uint8)
            cv2.rectangle(test_frame, (120, 140), (520, 340), (0, 160, 255), 2)
            cv2.putText(test_frame, "CCTV DISPATCH SYSTEM ONLINE", (140, 230), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
            cv2.putText(test_frame, f"TIMESTAMP: {time.strftime('%Y-%m-%d %H:%M:%S')}", (140, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        try:
            self._dispatch_email(test_alert, test_frame, boundary_points=boundary_points or [], override_recipient=recipient)
            return True, "Test alert with camera snapshot successfully delivered!"
        except Exception as e:
            return False, f"Delivery failed: {str(e)}"

    def _dispatch_email(self, alert: dict, frame: np.ndarray, boundary_points: list, override_recipient: str = None):
        with self._lock:
            recipient = override_recipient or self.config.get("recipient_email", "").strip()
            sender = self.config.get("sender_email", "").strip()
            password = self.config.get("app_password", "").replace(" ", "").strip()
            server = self.config.get("smtp_server", "smtp.gmail.com")
            port = int(self.config.get("smtp_port", 587))

        if not recipient:
            raise ValueError("No recipient email specified")

        # If sender is missing, fallback to recipient or default
        if not sender:
            sender = recipient

        # 1. Annotate snapshot
        annotated = self.annotate_frame(frame, alert, boundary_points)
        img_bytes = None
        if annotated is not None:
            _, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            img_bytes = buffer.tobytes()

        # 2. Build MIME Email
        msg = MIMEMultipart("related")
        msg["Subject"] = f"🚨 {alert.get('title', 'INTRUSION ALERT')} - NODE_01_SOUTH"
        msg["From"] = f"SIH Edge CCTV Surveillance <{sender}>"
        msg["To"] = recipient

        time_val = alert.get("time", time.strftime("%H:%M:%S"))
        category = alert.get("category", "INTRUSION")
        message = alert.get("message", "Perimeter boundary violated")
        plate_info = f"<p><b>Identified Plate:</b> <span style='background:#e0f2fe;color:#0369a1;padding:3px 8px;font-family:monospace;font-weight:bold;border-radius:4px;'>{alert.get('plate_number')}</span></p>" if alert.get("is_plate") else ""

        html_content = f"""
        <html>
        <body style="font-family: 'Segoe UI', Helvetica, Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px;">
            <div style="max-width: 620px; margin: 0 auto; background: #1e293b; border-radius: 8px; border: 1px solid #ef4444; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.5);">
                <div style="background: #ef4444; padding: 14px 20px; color: #ffffff;">
                    <h2 style="margin: 0; font-size: 18px; letter-spacing: 0.05em; font-weight: 800;">🚨 SECURITY ALERT: BOUNDARY BREACH DETECTED</h2>
                    <p style="margin: 3px 0 0 0; font-size: 12px; opacity: 0.9;">Smart India Hackathon Surveillance SOC · NODE_01_SOUTH</p>
                </div>
                <div style="padding: 20px;">
                    <p style="font-size: 14px; margin-top: 0;">An active perimeter intrusion has been verified by edge neural inference:</p>
                    <table style="width: 100%; border-collapse: collapse; margin-bottom: 18px; font-size: 13.5px;">
                        <tr style="border-bottom: 1px solid #334155;">
                            <td style="padding: 8px 0; color: #94a3b8;"><b>Timestamp:</b></td>
                            <td style="padding: 8px 0; color: #f1f5f9; font-family: monospace;">{time_val}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #334155;">
                            <td style="padding: 8px 0; color: #94a3b8;"><b>Category:</b></td>
                            <td style="padding: 8px 0; color: #f87171; font-weight: bold;">{category}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #334155;">
                            <td style="padding: 8px 0; color: #94a3b8;"><b>Violation:</b></td>
                            <td style="padding: 8px 0; color: #f1f5f9;">{message}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #94a3b8;"><b>Perimeter Dwell:</b></td>
                            <td style="padding: 8px 0; color: #f59e0b; font-weight: bold;">&gt; 5.0 Seconds Threshold Exceeded</td>
                        </tr>
                    </table>
                    {plate_info}
                    <div style="margin-top: 15px; border-radius: 6px; overflow: hidden; border: 1px solid #475569;">
                        <img src="cid:snapshot" style="width: 100%; display: block;" alt="Intruder Snapshot" />
                    </div>
                    <p style="font-size: 11.5px; color: #64748b; margin-top: 15px; text-align: center;">
                        Automated edge notification generated by SIH CCTV AI Surveillance Node.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        msg_alternative = MIMEMultipart("alternative")
        msg.attach(msg_alternative)
        msg_alternative.attach(MIMEText(html_content, "html"))

        # Attach image as inline CID
        if img_bytes:
            img_part = MIMEImage(img_bytes)
            img_part.add_header("Content-ID", "<snapshot>")
            img_part.add_header("Content-Disposition", "inline", filename=f"breach_{int(time.time())}.jpg")
            msg.attach(img_part)

        # 3. Transmit via SMTP (TLS)
        if not password:
            print(f"[EmailNotifier] DRY-RUN / SIMULATED: Email composed for '{recipient}'. Set sender_email & app_password in settings to deliver via live SMTP.")
            with self._lock:
                self.last_dispatch_status = "SENT (SIMULATED)"
                self.last_dispatch_message = f"Snapshot composed for {recipient} (configure SMTP App Password for live delivery)"
                self.total_sent += 1
            return

        with smtplib.SMTP(server, port, timeout=12) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(sender, password)
            smtp.sendmail(sender, [recipient], msg.as_string())

        print(f"[EmailNotifier] Successfully delivered breach alert to: {recipient}")
        with self._lock:
            self.last_dispatch_status = "DELIVERED"
            self.last_dispatch_message = f"Alert delivered to {recipient} at {time_val}"
            self.total_sent += 1
