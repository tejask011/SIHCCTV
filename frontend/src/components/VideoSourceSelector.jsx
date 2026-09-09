// VideoSourceSelector.jsx
// Unified Source Control Bar — Obsidian Surveillance & Precision Video Telemetry.

import { useState } from 'react';
import { API } from '../config';

export default function VideoSourceSelector({ isConnected, onConnected, onError, onStopped }) {
  const [mode, setMode]       = useState('webcam'); // 'webcam' | 'url'
  const [url, setUrl]         = useState('http://192.168.1.10:8080/video');
  const [loading, setLoading] = useState(false);

  async function connect() {
    setLoading(true);
    onError(null);
    try {
      const body = mode === 'webcam'
        ? { type: 'webcam' }
        : { type: 'url', url };

      const res  = await fetch(`${API}/api/source`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
      });
      const data = await res.json();

      if (data.ok) {
        onConnected(mode === 'webcam' ? 'Laptop Webcam' : url);
      } else {
        onError(data.error || 'Failed to connect');
      }
    } catch (e) {
      onError('Cannot reach backend — is it running on port 8000?');
    } finally {
      setLoading(false);
    }
  }

  async function disconnect() {
    await fetch(`${API}/api/source`, { method: 'DELETE' }).catch(() => {});
    onStopped();
  }

  return (
    <div className="source-control-bar">
      <div className="source-control-left">
        <span className="source-label-caps">
          <span className="status-dot-led" style={{ color: 'var(--primary)' }} />
          VIDEO SOURCE
        </span>

        {/* Segmented Source Switch */}
        <div className="source-toggle-group">
          <button
            id="btn-webcam"
            className={`source-pill-btn ${mode === 'webcam' ? 'active' : ''}`}
            onClick={() => setMode('webcam')}
            type="button"
          >
            <span>💻</span> Laptop Webcam
          </button>
          <button
            id="btn-url"
            className={`source-pill-btn ${mode === 'url' ? 'active' : ''}`}
            onClick={() => setMode('url')}
            type="button"
          >
            <span>📡</span> Stream URL
          </button>
        </div>

        {/* Action triggers */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button
            id="btn-connect"
            className="btn-action-connect"
            onClick={connect}
            disabled={loading || isConnected}
            type="button"
          >
            {loading ? '⏳ CONNECTING…' : '▶ CONNECT'}
          </button>

          <button
            id="btn-disconnect"
            className="btn-action-stop"
            onClick={disconnect}
            disabled={!isConnected && !loading}
            type="button"
          >
            <span>⏹</span> Stop
          </button>
        </div>
      </div>

      {/* Stream Hardware Telemetry Readout */}
      <div className="source-telemetry-meta">
        <span className="status-dot-led" style={{ color: isConnected ? 'var(--secondary)' : 'var(--text-muted)' }} />
        <span>FPS: <strong style={{ color: isConnected ? '#fff' : 'inherit' }}>{isConnected ? '30' : '--'}</strong></span>
        <span>/</span>
        <span>Bitrate: <strong style={{ color: isConnected ? '#fff' : 'inherit' }}>{isConnected ? '2400' : '0'} kbps</strong></span>
      </div>

      {/* Inline URL input popover when Stream URL mode is selected */}
      {mode === 'url' && (
        <div className="url-input-popover">
          <input
            id="stream-url-input"
            className="url-input-machined"
            type="text"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="http://192.168.x.x:8080/video or rtsp://..."
            onKeyDown={e => e.key === 'Enter' && connect()}
          />
        </div>
      )}
    </div>
  );
}

