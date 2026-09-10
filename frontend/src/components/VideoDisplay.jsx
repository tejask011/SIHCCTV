// VideoDisplay.jsx
// Shows the MJPEG stream from the backend and handles boundary drawing.
//
// Coordinate contract:
//   - The user clicks on the <img> element (displayed size may differ from frame size).
//   - We compute click position RELATIVE to the <img> element and normalise to [0..1].
//   - Backend receives normalised coords and scales them to actual frame pixels.
//   - This guarantees the drawn polygon maps correctly to the real video resolution.

import { useRef, useEffect, useState, useCallback } from 'react';
import { API, STREAM_URL } from '../config';

export default function VideoDisplay({
  isConnected,
  isDrawing,
  boundaryPoints,       // [[normX, normY], ...]  — managed by parent (App)
  onAddPoint,
  streamError,
  ocrData,
}) {
  const imgRef    = useRef(null);
  const canvasRef = useRef(null);
  const [scanning, setScanning] = useState(false);
  const [manualScanResult, setManualScanResult] = useState(null);
  const [dismissedOcrTs, setDismissedOcrTs] = useState(0);
  const [scanNotice, setScanNotice] = useState('');

  // Trigger immediate OCR scan on current live frame
  const handleScanNow = async () => {
    if (!isConnected || scanning) return;
    setScanning(true);
    setScanNotice('');
    try {
      const res = await fetch(`${API}/api/ocr/scan`, { method: 'POST' });
      const data = await res.json();
      if (data.ok && data.result?.detected) {
        setManualScanResult(data.result);
        setTimeout(() => setManualScanResult(null), 8000);
      } else {
        setScanNotice('No text or plate pattern recognized in current frame. Hold steady and try again.');
        setTimeout(() => setScanNotice(''), 4000);
      }
    } catch (err) {
      console.error('Scan error:', err);
      setScanNotice('Scan request failed');
      setTimeout(() => setScanNotice(''), 3000);
    } finally {
      setScanning(false);
    }
  };

  // Resize canvas to match the <img> rendered size
  const syncCanvas = useCallback(() => {
    const img = imgRef.current;
    const cv  = canvasRef.current;
    if (!img || !cv) return;
    cv.width  = img.clientWidth;
    cv.height = img.clientHeight;
  }, []);

  useEffect(() => {
    syncCanvas();
    const ro = new ResizeObserver(syncCanvas);
    if (imgRef.current) ro.observe(imgRef.current);
    return () => ro.disconnect();
  }, [syncCanvas]);

  // Draw the polygon preview on the canvas
  useEffect(() => {
    const cv  = canvasRef.current;
    const img = imgRef.current;
    if (!cv || !img) return;

    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);

    if (boundaryPoints.length === 0) return;

    // De-normalise: multiply by canvas display size
    const pts = boundaryPoints.map(([nx, ny]) => [
      nx * cv.width,
      ny * cv.height,
    ]);

    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);

    if (pts.length >= 3) {
      ctx.closePath();
      ctx.fillStyle = 'rgba(255, 0, 0, 0.15)';
      ctx.fill();
    }

    ctx.strokeStyle = '#ff3b3b';
    ctx.lineWidth   = 2;
    ctx.stroke();

    // Vertex dots + labels
    pts.forEach(([x, y], i) => {
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = '#ff3b3b';
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 11px Inter';
      ctx.fillText(i + 1, x + 7, y - 4);
    });
  }, [boundaryPoints]);

  function handleClick(e) {
    if (!isDrawing) return;

    const img    = imgRef.current;
    const rect   = img.getBoundingClientRect();
    const normX  = (e.clientX - rect.left)  / rect.width;
    const normY  = (e.clientY - rect.top)   / rect.height;

    // Clamp to [0..1]
    onAddPoint([
      Math.max(0, Math.min(1, normX)),
      Math.max(0, Math.min(1, normY)),
    ]);
  }

  const [showGrid, setShowGrid] = useState(false);
  const [zoom, setZoom]         = useState(1.0);
  const containerRef            = useRef(null);

  function toggleFullscreen() {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  }

  return (
    <div
      ref={containerRef}
      className="optical-stage"
      style={{ userSelect: 'none' }}
    >
      {/* Optical Corner HUD Markers */}
      <span className="optical-corner optical-corner-tl" />
      <span className="optical-corner optical-corner-tr" />
      <span className="optical-corner optical-corner-bl" />
      <span className="optical-corner optical-corner-br" />

      {/* Optical Grid Overlay */}
      {showGrid && <div className="optical-grid-overlay" />}

      {/* Top HUD Telemetry Bar */}
      <div className="hud-top-bar">
        <div className="hud-group-left">
          <div className="hud-pill rec">
            <span className="hud-pill rec-dot" />
            <span>REC 00:00:00</span>
          </div>
          <div className="hud-pill res">
            <span>1080p @ 30FPS</span>
          </div>
        </div>

        <div className="hud-pill inference">
          <span>((•)) AI INFERENCE: {isConnected ? 'ACTIVE' : 'IDLE'}</span>
        </div>
      </div>

      {/* Video stream or Idle State */}
      {isConnected ? (
        <div style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
        }}>
          <img
            id="video-feed"
            ref={imgRef}
            className="video-feed"
            src={`${STREAM_URL}?t=${Date.now()}`}
            alt="Live CCTV feed"
            style={{
              width: '100%',
              height: 'auto',
              maxHeight: '520px',
              objectFit: 'contain',
              cursor: isDrawing ? 'crosshair' : 'default',
              transform: `scale(${zoom})`,
              transition: 'transform 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
            }}
            onClick={handleClick}
            onLoad={syncCanvas}
            draggable={false}
          />
        </div>
      ) : (
        <div className="idle-viewport-screen">
          <div className="idle-camera-icon-box">
            <span>📷</span>
          </div>
          <div className="idle-title">NO ACTIVE SURVEILLANCE FEED CONNECTED</div>
          <div className="idle-subtext">
            Select Video Source in top control bar and press Connect to start real-time neural edge ingestion
          </div>
        </div>
      )}

      {/* Canvas overlay for drawing boundary */}
      <canvas
        ref={canvasRef}
        className={`video-canvas ${isDrawing ? 'drawing' : ''}`}
        onClick={isDrawing ? handleClick : undefined}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          pointerEvents: isDrawing ? 'all' : 'none',
          zIndex: 8,
        }}
      />

      {/* Active OCR / ANPR Floating Telemetry Overlay */}
      {(() => {
        if (!isConnected) return null;
        const activeOcr = manualScanResult || (ocrData?.detected ? ocrData : null);

        if (!activeOcr || !activeOcr.best_text) {
          if (scanNotice) {
            return (
              <div className="hud-anpr-card" style={{ borderColor: 'rgba(234, 179, 8, 0.5)', pointerEvents: 'none' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: '#fde047' }}>
                  ℹ {scanNotice}
                </div>
              </div>
            );
          }
          return null;
        }

        // If user manually dismissed this OCR scan, keep it dismissed
        const itemTs = activeOcr.timestamp || 0;
        if (dismissedOcrTs && itemTs && itemTs <= dismissedOcrTs) {
          return null;
        }

        // Auto-dismiss automatic detections after 3.5s; manual scans after 6s
        const nowSec = Date.now() / 1000;
        if (itemTs && (nowSec - itemTs > (manualScanResult ? 6.0 : 3.5))) {
          return null;
        }

        return (
          <div className="hud-anpr-card">
            <div className="hud-anpr-tag-row">
              <span className={`hud-anpr-badge ${activeOcr.is_plate ? 'plate' : 'text'}`}>
                {activeOcr.is_plate ? '🚘 ANPR PLATE DETECTED' : '📄 OCR TEXT READ'}
              </span>
              <span className="hud-anpr-confidence">
                {(activeOcr.confidence * 100).toFixed(0)}% CONF · {activeOcr.processing_ms}ms
              </span>
              <button
                type="button"
                onClick={() => {
                  setManualScanResult(null);
                  setDismissedOcrTs(activeOcr.timestamp || (Date.now() / 1000));
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  fontSize: 13,
                  marginLeft: 'auto',
                  pointerEvents: 'all'
                }}
                title="Dismiss"
              >
                ✕
              </button>
            </div>
            <div className="hud-anpr-value">
              {activeOcr.is_plate ? activeOcr.plate_number : activeOcr.best_text}
            </div>
            {activeOcr.label && (
              <div className="hud-anpr-meta">
                Source: {activeOcr.label.toUpperCase()} · Category: {activeOcr.category}
              </div>
            )}
          </div>
        );
      })()}

      {/* Bottom HUD Controls */}
      <div className="hud-bottom-bar">
        <div className="hud-zoom-control">
          <span>🔍 ZOOM:</span>
          <input
            type="range"
            min="1.0"
            max="2.5"
            step="0.1"
            value={zoom}
            onChange={e => setZoom(parseFloat(e.target.value))}
            className="zoom-slider-machined"
          />
          <span style={{ fontFamily: 'var(--font-mono)', minWidth: 32 }}>{zoom.toFixed(1)}x</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button
            type="button"
            className="hud-btn-action"
            onClick={handleScanNow}
            disabled={!isConnected || scanning}
            title="Immediately scan live camera view for vehicle license plates or book text"
            style={{
              color: scanning ? 'var(--secondary)' : '#38bdf8',
              borderColor: 'rgba(56, 189, 248, 0.4)',
              background: scanning ? 'rgba(56, 189, 248, 0.15)' : undefined
            }}
          >
            <span>{scanning ? '⏳' : '📸'}</span>
            <span>{scanning ? 'Scanning...' : 'Scan Plate / Text'}</span>
          </button>
          <button
            type="button"
            className="hud-btn-action"
            onClick={() => setShowGrid(prev => !prev)}
            style={{ color: showGrid ? 'var(--primary)' : undefined }}
          >
            <span>⊞</span> Grid
          </button>
          <button
            type="button"
            className="hud-btn-action"
            onClick={toggleFullscreen}
          >
            <span>⛶</span> Fullscreen
          </button>
        </div>
      </div>

      {streamError && (
        <div style={{
          position: 'absolute',
          bottom: 44,
          left: 14,
          right: 14,
          background: 'rgba(239, 68, 68, 0.9)',
          color: '#fff',
          padding: '8px 14px',
          borderRadius: 4,
          fontSize: 13,
          fontFamily: 'var(--font-mono)',
          zIndex: 20
        }}>
          ⚠ {streamError}
        </div>
      )}
    </div>
  );
}

