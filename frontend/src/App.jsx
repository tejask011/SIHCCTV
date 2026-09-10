// App.jsx
// Root component — wires together all features.

import { useState, useEffect, useRef, useCallback } from 'react';
import VideoSourceSelector  from './components/VideoSourceSelector';
import VideoDisplay         from './components/VideoDisplay';
import BoundaryControls     from './components/BoundaryControls';
import DetectionSummary     from './components/DetectionSummary';
import TelemetryTerminal    from './components/TelemetryTerminal';
import AlertPanel           from './components/AlertPanel';
import DetectionLogPanel    from './components/DetectionLogPanel';
import EmailAlertModal      from './components/EmailAlertModal';

import { API, WS_URL } from './config';

export default function App() {
  // ── Stream state ──────────────────────────────────────────────
  const [isConnected, setConnected]   = useState(false);
  const [sourceLabel, setSourceLabel] = useState('');
  const [streamError, setStreamError] = useState(null);

  // ── Detection / alert state (from WebSocket) ──────────────────
  const [summary, setSummary]                 = useState({ HUMAN: 0, ANIMAL: 0, VEHICLE: 0, OBJECT: 0 });
  const [alerts, setAlerts]                   = useState([]);
  const [detectionLog, setDetectionLog]       = useState([]);
  const [detectionMode, setDetectionMode]     = useState('all'); // 'all' or 'person_wearables'
  const [activeIntrusion, setActiveIntrusion] = useState(false);
  const [cameraBlocked, setCameraBlocked]     = useState(false);
  const [dwellTimes, setDwellTimes]           = useState({});  // idx→seconds
  const [ocrData, setOcrData]                 = useState(null);
  const [emailStatus, setEmailStatus]         = useState({});
  const [isEmailModalOpen, setEmailModalOpen] = useState(false);

  // ── Timestamps to ignore stale in-flight messages after user clears logs ──
  const alertsClearedAtRef = useRef(0);
  const detectLogClearedAtRef = useRef(0);

  // ── Boundary drawing state ────────────────────────────────────
  const [isDrawing, setDrawing]           = useState(false);
  const [boundaryPoints, setBoundaryPoints] = useState([]);   // [[normX, normY], ...]

  // ── WebSocket ─────────────────────────────────────────────────
  const wsRef = useRef(null);

  // ── Live Clock for Top Navbar ──────────────────────────────────
  const [clock, setClock] = useState(() => new Date().toLocaleTimeString());
  useEffect(() => {
    const timer = setInterval(() => {
      setClock(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const connectWS = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState < 2) return;

    const ws = new WebSocket(WS_URL);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.summary)                       setSummary(data.summary);
        if (data.alerts) {
          const freshAlerts = data.alerts.filter(a => (a.id || 0) > alertsClearedAtRef.current);
          setAlerts(freshAlerts);
        }
        if (data.detection_log) {
          const freshLogs = data.detection_log.filter(l => (l.id || 0) > detectLogClearedAtRef.current);
          setDetectionLog(freshLogs);
        }
        if (data.detection_mode)                 setDetectionMode(data.detection_mode);
        if (data.active_intrusion !== undefined) setActiveIntrusion(data.active_intrusion);
        if (data.camera_blocked !== undefined)   setCameraBlocked(data.camera_blocked);
        if (data.dwell_times)                    setDwellTimes(data.dwell_times);
        if (data.ocr)                            setOcrData(data.ocr);
        if (data.email_status)                   setEmailStatus(data.email_status);
        if (data.error)                          setStreamError(data.error);
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = () => {
      // Reconnect after 2 s if still connected
      setTimeout(() => { if (isConnected) connectWS(); }, 2000);
    };

    wsRef.current = ws;
  }, [isConnected]);

  useEffect(() => {
    connectWS();
    return () => wsRef.current?.close();
  }, [connectWS]);

  // Keep WS alive when connected
  useEffect(() => {
    if (isConnected) connectWS();
  }, [isConnected, connectWS]);

  // ── Source events ──────────────────────────────────────────────
  function handleConnected(label) {
    setConnected(true);
    setSourceLabel(label);
    setStreamError(null);
    setBoundaryPoints([]);
    setDrawing(false);
    setAlerts([]);
    setDetectionLog([]);
    setActiveIntrusion(false);
    setCameraBlocked(false);
    setDwellTimes({});
    const now = Date.now();
    alertsClearedAtRef.current = now;
    detectLogClearedAtRef.current = now;
    // Short delay then trigger WS reconnect to start receiving data
    setTimeout(connectWS, 500);
  }

  function handleStopped() {
    setConnected(false);
    setSourceLabel('');
    setDrawing(false);
    setBoundaryPoints([]);
    setAlerts([]);
    setDetectionLog([]);
    setSummary({ HUMAN: 0, ANIMAL: 0, VEHICLE: 0, OBJECT: 0 });
    setActiveIntrusion(false);
    setCameraBlocked(false);
    setDwellTimes({});
    setOcrData(null);
    const now = Date.now();
    alertsClearedAtRef.current = now;
    detectLogClearedAtRef.current = now;
  }

  // ── Boundary actions ───────────────────────────────────────────
  function handleAddPoint(normPt) {
    setBoundaryPoints(prev => [...prev, normPt]);
  }

  // Undo last boundary point
  function handleUndo() {
    setBoundaryPoints(prev => prev.slice(0, -1));
  }

  async function handleFinishBoundary() {
    if (boundaryPoints.length < 3) return;
    setDrawing(false);

    const res  = await fetch(`${API}/api/boundary`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ points: boundaryPoints }),
    });
    const data = await res.json();
    if (!data.ok) console.error('Boundary error:', data.error);
  }

  async function handleClearBoundary() {
    setBoundaryPoints([]);
    setDrawing(false);
    await fetch(`${API}/api/boundary`, { method: 'DELETE' }).catch(() => {});
  }

  // ── Log Clearing Actions (Both WS Instant Push & HTTP REST) ──
  async function handleClearAll() {
    const now = Date.now();
    alertsClearedAtRef.current = now;
    detectLogClearedAtRef.current = now;
    setAlerts([]);
    setDetectionLog([]);
    setActiveIntrusion(false);

    // Send instant clear command through WebSocket connection
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ action: 'clear_all' }));
      } catch { /* ignore */ }
    }
    // Also call HTTP backend endpoint to guarantee memory purge
    await fetch(`${API}/api/logs`, { method: 'DELETE' }).catch(() => {});
  }

  async function handleClearAlerts() {
    alertsClearedAtRef.current = Date.now();
    setAlerts([]);
    setActiveIntrusion(false);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ action: 'clear_alerts' }));
      } catch { /* ignore */ }
    }
    await fetch(`${API}/api/alerts`, { method: 'DELETE' }).catch(() => {});
  }

  async function handleClearDetectionLog() {
    detectLogClearedAtRef.current = Date.now();
    setDetectionLog([]);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ action: 'clear_detection_log' }));
      } catch { /* ignore */ }
    }
    await fetch(`${API}/api/detection-log`, { method: 'DELETE' }).catch(() => {});
  }

  async function handleSetMode(mode) {
    setDetectionMode(mode);
    try {
      await fetch(`${API}/api/detection-mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
    } catch (err) {
      console.error('Mode toggle failed:', err);
    }
  }

  // ── Render ─────────────────────────────────────────────────────
  return (
    <div className="app">
      {/* ── Top Navigation Bar ── */}
      <header className="header-nav">
        <div className="header-brand">
          <div className="header-shield-icon">🛡</div>
          <div className="header-title-group">
            <div className="title-row">
              <span className="brand-title">AI CCTV // VIDEO ANALYTICS</span>
              <span className="badge-amber">SIH SOC EDITION</span>
            </div>
            <div className="subtitle-row">
              <span>Smart India Hackathon</span>
              <span className="dot-sep">▪</span>
              <span>Intelligent Edge Security Surveillance</span>
              <span className="dot-sep">▪</span>
              <span className="node-id">NODE_01_SOUTH</span>
            </div>
          </div>
        </div>

        <div className="header-telemetry-right">
          {/* Email Dispatch Alert Setup Pill */}
          <button
            id="btn-email-dispatch"
            type="button"
            onClick={() => setEmailModalOpen(true)}
            className="telemetry-pill"
            style={{
              cursor: 'pointer',
              background: emailStatus?.enabled ? 'rgba(16, 185, 129, 0.15)' : 'var(--surface-container-low)',
              border: `1px solid ${emailStatus?.enabled ? 'var(--secondary)' : 'var(--outline)'}`,
              color: emailStatus?.enabled ? 'var(--secondary)' : 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              transition: 'all 0.2s',
            }}
            title="Configure automatic perimeter breach email dispatch with photo snapshot"
          >
            <span>📧</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700 }}>
              {emailStatus?.enabled ? 'EMAIL ALERTS: ON' : 'EMAIL ALERTS: OFF'}
            </span>
            {emailStatus?.enabled && emailStatus?.recipient_email && (
              <span style={{ fontSize: 11, opacity: 0.85, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                ({emailStatus.recipient_email})
              </span>
            )}
          </button>

          {/* Zone status pill */}
          <div className="telemetry-pill">
            <span
              className="status-dot-led"
              style={{ color: boundaryPoints.length >= 3 ? 'var(--secondary)' : 'var(--text-muted)' }}
            />
            <span>ZONE: {boundaryPoints.length >= 3 ? 'ARMED' : 'NOT SET'}</span>
          </div>

          {/* Real-time digital clock */}
          <div className="telemetry-pill">
            <span style={{ fontSize: 14 }}>🕒</span>
            <span>{clock}</span>
          </div>

          {/* Live/Standby Pill */}
          <div className={`telemetry-pill-standby ${isConnected ? 'live' : ''}`}>
            <span className="status-dot-led pulsing" />
            <span>{isConnected ? 'LIVE' : 'STANDBY'}</span>
          </div>
        </div>
      </header>

      {/* ── Main Container ── */}
      <main className="main-container">
        {/* Unified Source Control Bar directly above main viewport */}
        <VideoSourceSelector
          isConnected={isConnected}
          onConnected={handleConnected}
          onError={setStreamError}
          onStopped={handleStopped}
        />

        {streamError && (
          <div style={{
            marginBottom: 12,
            padding: '10px 14px',
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid var(--error)',
            borderRadius: 'var(--radius-xs)',
            color: '#fca5a5',
            fontFamily: 'var(--font-mono)',
            fontSize: 13,
          }}>
            ⚠ {streamError}
          </div>
        )}

        {/* ── Main Matrix Grid ── */}
        <div className="main-matrix-grid">
          {/* Left Column: Live Video Stream & Boundary Controls */}
          <div className="video-surveillance-container">
            {/* Viewport Channel & Filter Header */}
            <div className="video-bar-header">
              <div className="panel-header-title">
                <span className="status-dot-led" style={{ color: 'var(--secondary)' }} />
                <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 13.5, letterSpacing: '0.04em' }}>
                  LIVE VIDEO STREAM
                </span>
                <span className="badge-tag-sm">Viewport 01 · CH_A</span>
              </div>

              {/* Mode Switcher */}
              <div className="video-mode-toggle">
                <button
                  id="btn-mode-all"
                  type="button"
                  className={`mode-pill-btn ${detectionMode === 'all' ? 'active' : ''}`}
                  onClick={() => handleSetMode('all')}
                  title="Detect all objects: bottle, laptop, phone, table, chair, etc."
                >
                  <span>⚖</span> All Objects
                </button>
                <button
                  id="btn-mode-wearables"
                  type="button"
                  className={`mode-pill-btn ${detectionMode === 'person_wearables' ? 'active' : ''}`}
                  onClick={() => handleSetMode('person_wearables')}
                  title="Filter strictly to human beings & wearable accessories"
                >
                  <span>👤</span> Person &amp; Wearables Only
                </button>
              </div>
            </div>

            {/* Viewport Optical Stage */}
            <VideoDisplay
              isConnected={isConnected}
              isDrawing={isDrawing}
              boundaryPoints={boundaryPoints}
              onAddPoint={handleAddPoint}
              streamError={streamError}
              ocrData={ocrData}
            />

            {/* Boundary Toolbar */}
            <BoundaryControls
              isDrawing={isDrawing}
              isConnected={isConnected}
              pointCount={boundaryPoints.length}
              onStartDraw={() => setDrawing(true)}
              onUndo={handleUndo}
              onFinishDraw={handleFinishBoundary}
              onClear={handleClearBoundary}
            />
          </div>

          {/* Right Column: Telemetry Sidecar Stack */}
          <aside className="telemetry-stack">
            {/* Real-time Detection Summary with Radar Graphic */}
            <DetectionSummary
              summary={summary}
              activeIntrusion={activeIntrusion}
            />

            {/* Unified Tabbed Telemetry Terminal (Alerts, Detections & All Logs) */}
            <TelemetryTerminal
              alerts={alerts}
              detectionLog={detectionLog}
              activeIntrusion={activeIntrusion}
              cameraBlocked={cameraBlocked}
              dwellTimes={dwellTimes}
              onClearAlerts={handleClearAlerts}
              onClearDetectionLog={handleClearDetectionLog}
              onClearAll={handleClearAll}
            />
          </aside>
        </div>
      </main>

      {/* Email Alert Configuration Modal */}
      <EmailAlertModal
        isOpen={isEmailModalOpen}
        onClose={() => setEmailModalOpen(false)}
        emailStatus={emailStatus}
      />
    </div>
  );
}

