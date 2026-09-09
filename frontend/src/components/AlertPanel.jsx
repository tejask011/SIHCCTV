// AlertPanel.jsx
// Incident Alert Stream Terminal — Obsidian Surveillance & Precision Video Telemetry.

const DWELL_SEC = 5; // must match backend alerts.py DWELL_SEC

export default function AlertPanel({ alerts = [], activeIntrusion = false, dwellTimes = {}, onClear }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* Active intrusion warning notification */}
      {activeIntrusion && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.15)',
          border: '1px solid var(--error)',
          borderRadius: 'var(--radius-xs)',
          padding: '8px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          animation: 'pulse-banner 1.2s infinite'
        }}>
          <span style={{ fontSize: 18 }}>🚨</span>
          <div>
            <div style={{
              fontFamily: 'var(--font-display)',
              fontSize: 12,
              fontWeight: 700,
              color: 'var(--error)',
              letterSpacing: '0.04em'
            }}>
              ACTIVE INTRUSION DETECTED
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: '#fca5a5' }}>
              Restricted boundary violated — continuous dwell threshold exceeded
            </div>
          </div>
        </div>
      )}

      {/* Dwell timer countdown meters */}
      {Object.keys(dwellTimes).length > 0 && !activeIntrusion && (
        <div style={{
          background: 'var(--surface-container-low)',
          border: '1px solid var(--outline)',
          borderRadius: 'var(--radius-xs)',
          padding: '8px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}>
          {Object.entries(dwellTimes).map(([idx, secs]) => {
            const pct = Math.min((secs / DWELL_SEC) * 100, 100);
            return (
              <div key={idx}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10.5,
                  color: 'var(--primary)',
                  marginBottom: 3
                }}>
                  <span>⏱ Object in perimeter</span>
                  <span>{secs.toFixed(1)}s / {DWELL_SEC}s</span>
                </div>
                <div style={{ height: 4, background: 'var(--surface-container-lowest)', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${pct}%`,
                    background: pct >= 100 ? 'var(--error)' : 'var(--primary)',
                    borderRadius: 2,
                    transition: 'width 0.2s',
                  }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Incident Alert Stream Terminal Card */}
      <div className="telemetry-terminal-card">
        {/* Terminal Header */}
        <div className="telemetry-terminal-header">
          <div className="telemetry-terminal-title">
            <span>&gt;_</span>
            <span>INCIDENT ALERT STREAM</span>
          </div>

          <div className="telemetry-terminal-actions">
            <span className="pill-count-tag alerts">
              {alerts.length} ALERTS
            </span>
            <button
              id="btn-clear-alerts"
              type="button"
              className="btn-terminal-clear"
              onClick={onClear}
              title="Clear all alerts"
            >
              <span>⊘</span> Clear
            </button>
          </div>
        </div>

        {/* Terminal Console Body */}
        <div className="telemetry-terminal-body">
          {alerts.length === 0 ? (
            <div className="terminal-prompt-line">
              <span className="prompt-prefix">root@sih-soc:~#</span>
              <span className="prompt-message">perimeter secure — zero active breaches detected.</span>
              <span className="blinking-caret amber" />
            </div>
          ) : (
            alerts.map(alert => (
              <div key={alert.id} className="terminal-log-row">
                <span className="terminal-log-time">[{alert.time}]</span>
                <span className="terminal-log-tag alert">ALERT</span>
                <span className="terminal-log-label" style={{ color: '#fca5a5' }}>
                  {alert.message}
                </span>
                <span className="terminal-log-zone breach">BREACH</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}


