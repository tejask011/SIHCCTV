// App.jsx
// Root component — wires together all features.

import { useState, useEffect, useRef, useCallback } from 'react';
import VideoSourceSelector  from './components/VideoSourceSelector';
import VideoDisplay         from './components/VideoDisplay';
import BoundaryControls     from './components/BoundaryControls';
import DetectionSummary     from './components/DetectionSummary';
import AlertPanel           from './components/AlertPanel';
import DetectionLogPanel    from './components/DetectionLogPanel';

const API    = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws';

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
  const [dwellTimes, setDwellTimes]           = useState({});  // idx→seconds

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
        if (data.alerts)                         setAlerts(data.alerts);
        if (data.detection_log)                  setDetectionLog(data.detection_log);
        if (data.detection_mode)                 setDetectionMode(data.detection_mode);
        if (data.active_intrusion !== undefined) setActiveIntrusion(data.active_intrusion);
        if (data.dwell_times)                    setDwellTimes(data.dwell_times);
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
    setActiveIntrusion(false);
    setDwellTimes({});
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
    setDwellTimes({});
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

  async function handleClearAlerts() {
    setAlerts([]);
    setActiveIntrusion(false);
    await fetch(`${API}/api/alerts`, { method: 'DELETE' }).catch(() => {});
  }

  async function handleClearDetectionLog() {
    setDetectionLog([]);
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
            <span style={{ fontSize: 12 }}>🕒</span>
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
            padding: '8px 12px',
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid var(--error)',
            borderRadius: 'var(--radius-xs)',
            color: '#fca5a5',
            fontFamily: 'var(--font-mono)',
            fontSize: 11.5,
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
                <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 12, letterSpacing: '0.04em' }}>
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

            {/* Incident Alert Stream Terminal */}
            <AlertPanel
              alerts={alerts}
              activeIntrusion={activeIntrusion}
              dwellTimes={dwellTimes}
              onClear={handleClearAlerts}
            />

            {/* Detection Log Stream Terminal */}
            <DetectionLogPanel
              log={detectionLog}
              onClear={handleClearDetectionLog}
            />
          </aside>
        </div>
      </main>
    </div>
  );
}

