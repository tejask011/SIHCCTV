// TelemetryTerminal.jsx
// Tabbed Terminal Console for Incident Alerts, Detection Logs & System Telemetry.
// Fits within the viewport with ZERO scrolling needed, with instant "Clear All" capability.

import { useState, useEffect, useRef } from 'react';

const DWELL_SEC = 5; // must match backend alerts.py DWELL_SEC

export default function TelemetryTerminal({
  alerts = [],
  detectionLog = [],
  activeIntrusion = false,
  cameraBlocked = false,
  dwellTimes = {},
  onClearAlerts,
  onClearDetectionLog,
  onClearAll,
}) {
  const [activeTab, setActiveTab] = useState('alerts'); // 'alerts' | 'detections' | 'plates' | 'all'
  const listRef = useRef(null);

  // Filter plates specifically for NO. PLATES tab
  const plateEntries = detectionLog.filter(d => d.category === 'NO. PLATES' || d.emoji === '🚘');

  // Automatically switch to 'alerts' tab when camera is blocked or new alert arrives
  useEffect(() => {
    if (cameraBlocked) {
      setActiveTab('alerts');
    }
  }, [cameraBlocked]);

  useEffect(() => {
    if (alerts.length > 0 && alerts[0]?.category === 'TAMPER') {
      setActiveTab('alerts');
    }
  }, [alerts]);

  // Auto-scroll terminal body to top when new events arrive
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = 0;
    }
  }, [alerts.length, detectionLog.length, activeTab]);

  // Combine alerts and detections for "All Events" view, sorted newest first
  const combinedEntries = [
    ...alerts.map(a => ({ ...a, _kind: 'alert' })),
    ...detectionLog.map(d => ({ ...d, _kind: 'detection' }))
  ].sort((a, b) => (b.id || 0) - (a.id || 0));

  return (
    <div className="telemetry-terminal-container" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {/* ── Camera Occlusion / Tamper Hazard Banner ── */}
      {cameraBlocked && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.22)',
          border: '2px solid var(--error)',
          borderRadius: 'var(--radius-xs)',
          padding: '12px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          animation: 'pulse-banner 0.9s infinite',
          boxShadow: '0 0 16px rgba(239, 68, 68, 0.4)'
        }}>
          <span style={{ fontSize: 26 }}>🚫</span>
          <div style={{ flex: 1 }}>
            <div style={{
              fontFamily: 'var(--font-display)',
              fontSize: 14.5,
              fontWeight: 800,
              color: '#fee2e2',
              letterSpacing: '0.04em',
              textTransform: 'uppercase'
            }}>
              CRITICAL: CAMERA OCCLUSION / FEED BLOCKED
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: '#fca5a5', marginTop: 2 }}>
              Camera lens covered or visual feed obstructed — logged in Alert tab
            </div>
          </div>
          <span className="badge-tag-sm" style={{ background: 'var(--error)', color: '#fff', fontWeight: 700 }}>
            TAMPER
          </span>
        </div>
      )}

      {/* ── Active Intrusion Warning Banner (when not occluded) ── */}
      {activeIntrusion && !cameraBlocked && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.15)',
          border: '1px solid var(--error)',
          borderRadius: 'var(--radius-xs)',
          padding: '10px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          animation: 'pulse-banner 1.2s infinite'
        }}>
          <span style={{ fontSize: 22 }}>🚨</span>
          <div>
            <div style={{
              fontFamily: 'var(--font-display)',
              fontSize: 14,
              fontWeight: 700,
              color: 'var(--error)',
              letterSpacing: '0.04em'
            }}>
              ACTIVE INTRUSION DETECTED
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: '#fca5a5' }}>
              Restricted boundary violated — dwell threshold exceeded
            </div>
          </div>
        </div>
      )}

      {/* ── Dwell Timer Progress Meters ── */}
      {Object.keys(dwellTimes).length > 0 && !activeIntrusion && !cameraBlocked && (
        <div style={{
          background: 'var(--surface-container-low)',
          border: '1px solid var(--outline)',
          borderRadius: 'var(--radius-xs)',
          padding: '10px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: 5,
        }}>
          {Object.entries(dwellTimes).map(([idx, secs]) => {
            const pct = Math.min((secs / DWELL_SEC) * 100, 100);
            return (
              <div key={idx}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12.5,
                  color: 'var(--primary)',
                  marginBottom: 4
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

      {/* ── Main Tabbed Telemetry Console Card ── */}
      <div className="telemetry-terminal-card">
        {/* Terminal Tab Bar & Actions */}
        <div className="telemetry-terminal-header" style={{ flexDirection: 'column', gap: 6, padding: '8px 8px 6px 8px' }}>
          {/* Tab Navigation Grid - 4 equal columns */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
            gap: 4,
            width: '100%'
          }}>
            <button
              id="tab-btn-alerts"
              type="button"
              className={`mode-pill-btn ${activeTab === 'alerts' ? 'active' : ''}`}
              style={{
                fontSize: 11,
                padding: '5px 2px',
                justifyContent: 'center',
                gap: 4,
                width: '100%',
                minWidth: 0,
                borderColor: activeTab === 'alerts' ? (cameraBlocked || alerts.length > 0 ? 'var(--error)' : 'var(--primary)') : 'transparent',
                background: activeTab === 'alerts' ? (cameraBlocked || alerts.length > 0 ? 'rgba(239, 68, 68, 0.2)' : 'var(--surface-container-low)') : 'transparent',
                color: activeTab === 'alerts' ? (cameraBlocked || alerts.length > 0 ? '#fca5a5' : 'var(--primary)') : 'var(--text-muted)'
              }}
              onClick={() => setActiveTab('alerts')}
              title="Alert logs"
            >
              <span>🚨</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>ALERTS</span>
              <span className="pill-count-tag alerts" style={{ marginLeft: 2, padding: '1px 4px', fontSize: 9.5 }}>
                {alerts.length}
              </span>
            </button>

            <button
              id="tab-btn-detections"
              type="button"
              className={`mode-pill-btn ${activeTab === 'detections' ? 'active' : ''}`}
              style={{
                fontSize: 11,
                padding: '5px 2px',
                justifyContent: 'center',
                gap: 4,
                width: '100%',
                minWidth: 0
              }}
              onClick={() => setActiveTab('detections')}
              title="Detection logs"
            >
              <span>📋</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>DETECT</span>
              <span className="pill-count-tag entries" style={{ marginLeft: 2, padding: '1px 4px', fontSize: 9.5 }}>
                {detectionLog.length}
              </span>
            </button>

            <button
              id="tab-btn-plates"
              type="button"
              className={`mode-pill-btn ${activeTab === 'plates' ? 'active' : ''}`}
              style={{
                fontSize: 11,
                padding: '5px 2px',
                justifyContent: 'center',
                gap: 4,
                width: '100%',
                minWidth: 0,
                borderColor: activeTab === 'plates' ? '#38bdf8' : 'transparent',
                background: activeTab === 'plates' ? 'rgba(56, 189, 248, 0.15)' : 'transparent',
                color: activeTab === 'plates' ? '#38bdf8' : 'var(--text-muted)'
              }}
              onClick={() => setActiveTab('plates')}
              title="License plates logs"
            >
              <span>🚘</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>PLATES</span>
              <span className="pill-count-tag" style={{ marginLeft: 2, padding: '1px 4px', fontSize: 9.5, background: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.4)' }}>
                {plateEntries.length}
              </span>
            </button>

            <button
              id="tab-btn-all"
              type="button"
              className={`mode-pill-btn ${activeTab === 'all' ? 'active' : ''}`}
              style={{
                fontSize: 11,
                padding: '5px 2px',
                justifyContent: 'center',
                gap: 4,
                width: '100%',
                minWidth: 0
              }}
              onClick={() => setActiveTab('all')}
              title="All telemetry logs"
            >
              <span>⚡</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>ALL</span>
              <span className="pill-count-tag" style={{ marginLeft: 2, padding: '1px 4px', fontSize: 9.5, background: 'rgba(245, 158, 11, 0.15)', color: 'var(--primary)', border: '1px solid rgba(245, 158, 11, 0.4)' }}>
                {alerts.length + detectionLog.length}
              </span>
            </button>
          </div>

          {/* Action Sub-Bar */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            width: '100%',
            paddingTop: 5,
            borderTop: '1px solid rgba(255, 255, 255, 0.05)'
          }}>
            <span style={{
              fontSize: 10.5,
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-muted)',
              letterSpacing: '0.04em',
              display: 'flex',
              alignItems: 'center',
              gap: 5
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', display: 'inline-block', boxShadow: '0 0 6px #10b981' }} />
              TELEMETRY STREAM
            </span>

            {/* Action Buttons */}
            <div className="telemetry-terminal-actions" style={{ gap: 5 }}>
              <button
                id="btn-clear-all-logs"
                type="button"
                className="btn-terminal-clear"
                style={{
                  color: '#f87171',
                  border: '1px solid rgba(239, 68, 68, 0.35)',
                  background: 'rgba(239, 68, 68, 0.1)',
                  padding: '2px 8px',
                  fontSize: 11,
                  fontWeight: 700,
                  borderRadius: 4
                }}
                onClick={onClearAll}
                title="Permanently wipe ALL logs (both Alerts & Detections)"
              >
                <span>⊘</span> Clear All
              </button>

              {activeTab === 'alerts' && alerts.length > 0 && (
                <button
                  id="btn-clear-alerts"
                  type="button"
                  className="btn-terminal-clear"
                  style={{ padding: '2px 8px', fontSize: 11, borderRadius: 4 }}
                  onClick={onClearAlerts}
                  title="Clear alerts only"
                >
                  Clear Tab
                </button>
              )}

              {activeTab === 'detections' && detectionLog.length > 0 && (
                <button
                  id="btn-clear-detection-log"
                  type="button"
                  className="btn-terminal-clear"
                  style={{ padding: '2px 8px', fontSize: 11, borderRadius: 4 }}
                  onClick={onClearDetectionLog}
                  title="Clear detection log only"
                >
                  Clear Tab
                </button>
              )}

              {activeTab === 'plates' && plateEntries.length > 0 && (
                <button
                  id="btn-clear-plates-log"
                  type="button"
                  className="btn-terminal-clear"
                  style={{ padding: '2px 8px', fontSize: 11, borderRadius: 4 }}
                  onClick={onClearDetectionLog}
                  title="Clear plates log only"
                >
                  Clear Tab
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Terminal Body Console */}
        <div ref={listRef} className="telemetry-terminal-body" style={{ maxHeight: 310, minHeight: 180 }}>
          {/* TAB 1: ALERTS */}
          {activeTab === 'alerts' && (
            alerts.length === 0 ? (
              <div className="terminal-prompt-line">
                <span className="prompt-prefix">root@sih-soc:~#</span>
                <span className="prompt-message">perimeter secure — zero active alerts or camera blockages detected.</span>
                <span className="blinking-caret amber" />
              </div>
            ) : (
              alerts.map(alert => {
                const isTamper = alert.category === 'TAMPER' || alert.title?.includes('BLOCKED') || alert.title?.includes('OCCLUSION');
                return (
                  <div key={alert.id} className="terminal-log-row">
                    <span className="terminal-log-time">[{alert.time}]</span>
                    <span
                      className={`terminal-log-tag ${isTamper ? 'breach' : 'alert'}`}
                      style={isTamper ? { background: 'var(--error)', color: '#fff', fontWeight: 800 } : {}}
                    >
                      {isTamper ? 'TAMPER' : 'ALERT'}
                    </span>
                    <span className="terminal-log-label" style={{ color: isTamper ? '#fecaca' : '#fca5a5' }}>
                      {alert.message}
                    </span>
                    <span className={`terminal-log-zone ${isTamper ? 'breach' : 'breach'}`}>
                      {isTamper ? 'BLOCKED' : 'BREACH'}
                    </span>
                  </div>
                );
              })
            )
          )}

          {/* TAB 2: DETECTIONS */}
          {activeTab === 'detections' && (
            detectionLog.length === 0 ? (
              <div className="terminal-prompt-line">
                <span className="prompt-prefix teal">root@sih-soc:~#</span>
                <span className="prompt-message">stream active — all detection logs cleared.</span>
                <span className="blinking-caret teal" />
              </div>
            ) : (
              detectionLog.map(entry => {
                const confPct = Math.round(entry.confidence * 100);
                const isTamper = entry.category === 'TAMPER';
                const isPlate = entry.category === 'NO. PLATES' || entry.emoji === '🚘';

                return (
                  <div key={entry.id} className="terminal-log-row">
                    <span className="terminal-log-time">[{entry.time}]</span>
                    <span
                      className={`terminal-log-tag ${isTamper ? 'breach' : isPlate ? 'detect' : 'detect'}`}
                      style={isPlate ? { background: '#0284c7', color: '#fff', fontWeight: 700 } : isTamper ? { background: 'var(--error)', color: '#fff' } : {}}
                    >
                      {isTamper ? 'TAMPER' : isPlate ? '🚘 PLATE' : 'DETECT'}
                    </span>
                    <span
                      className="terminal-log-label"
                      style={isPlate ? { color: '#38bdf8', fontWeight: 700, letterSpacing: '0.04em' } : {}}
                    >
                      {entry.label}
                    </span>
                    {!isTamper && (
                      <span className="terminal-log-conf" style={isPlate ? { color: '#7dd3fc' } : {}}>
                        {confPct}%
                      </span>
                    )}
                    {entry.intruding ? (
                      <span className="terminal-log-zone breach">
                        {isTamper ? 'BLOCKED' : '⚠ IN ZONE'}
                      </span>
                    ) : isPlate ? (
                      <span className="terminal-log-zone safe" style={{ borderColor: 'rgba(56, 189, 248, 0.4)', color: '#38bdf8' }}>
                        ✓ ANPR
                      </span>
                    ) : (
                      <span className="terminal-log-zone safe">
                        ✓ SAFE
                      </span>
                    )}
                  </div>
                );
              })
            )
          )}

          {/* TAB 3: NO. PLATES */}
          {activeTab === 'plates' && (
            plateEntries.length === 0 ? (
              <div className="terminal-prompt-line">
                <span className="prompt-prefix cyan" style={{ color: '#38bdf8' }}>root@sih-anpr:~#</span>
                <span className="prompt-message" style={{ color: '#bae6fd' }}>anpr engine active — vehicle number plates detected on video or snapshot will be logged here.</span>
                <span className="blinking-caret cyan" style={{ background: '#38bdf8' }} />
              </div>
            ) : (
              plateEntries.map(entry => {
                const confPct = Math.round(entry.confidence * 100);
                return (
                  <div key={entry.id} className="terminal-log-row" style={{ background: 'rgba(56, 189, 248, 0.05)', borderLeft: '3px solid #38bdf8' }}>
                    <span className="terminal-log-time">[{entry.time}]</span>
                    <span className="terminal-log-tag" style={{ background: '#0284c7', color: '#fff', fontWeight: 700 }}>
                      🚘 NO. PLATES
                    </span>
                    <span className="terminal-log-label" style={{ color: '#38bdf8', fontWeight: 800, fontSize: 13.5, letterSpacing: '0.06em' }}>
                      {entry.label}
                    </span>
                    <span className="terminal-log-conf" style={{ color: '#7dd3fc' }}>
                      {confPct}%
                    </span>
                    <span className="terminal-log-zone safe" style={{ borderColor: 'rgba(56, 189, 248, 0.4)', color: '#38bdf8' }}>
                      ✓ VERIFIED
                    </span>
                  </div>
                );
              })
            )
          )}

          {/* TAB 4: ALL EVENTS */}
          {activeTab === 'all' && (
            combinedEntries.length === 0 ? (
              <div className="terminal-prompt-line">
                <span className="prompt-prefix">root@sih-soc:~#</span>
                <span className="prompt-message">telemetry nominal — all logs cleared.</span>
                <span className="blinking-caret amber" />
              </div>
            ) : (
              combinedEntries.map(item => {
                if (item._kind === 'alert') {
                  const isTamper = item.category === 'TAMPER';
                  return (
                    <div key={`alt-${item.id}`} className="terminal-log-row">
                      <span className="terminal-log-time">[{item.time}]</span>
                      <span className="terminal-log-tag alert" style={isTamper ? { background: 'var(--error)', color: '#fff' } : {}}>
                        {isTamper ? 'TAMPER' : 'ALERT'}
                      </span>
                      <span className="terminal-log-label" style={{ color: '#fca5a5' }}>
                        {item.message}
                      </span>
                      <span className="terminal-log-zone breach">
                        {isTamper ? 'BLOCKED' : 'BREACH'}
                      </span>
                    </div>
                  );
                } else {
                  const confPct = Math.round(item.confidence * 100);
                  const isTamper = item.category === 'TAMPER';
                  const isPlate = item.category === 'NO. PLATES' || item.emoji === '🚘';

                  return (
                    <div key={`det-${item.id}`} className="terminal-log-row">
                      <span className="terminal-log-time">[{item.time}]</span>
                      <span
                        className={`terminal-log-tag ${isTamper ? 'breach' : 'detect'}`}
                        style={isPlate ? { background: '#0284c7', color: '#fff', fontWeight: 700 } : isTamper ? { background: 'var(--error)', color: '#fff' } : {}}
                      >
                        {isTamper ? 'TAMPER' : isPlate ? '🚘 PLATE' : 'DETECT'}
                      </span>
                      <span
                        className="terminal-log-label"
                        style={isPlate ? { color: '#38bdf8', fontWeight: 700, letterSpacing: '0.04em' } : {}}
                      >
                        {item.label}
                      </span>
                      {!isTamper && (
                        <span className="terminal-log-conf" style={isPlate ? { color: '#7dd3fc' } : {}}>
                          {confPct}%
                        </span>
                      )}
                      {item.intruding ? (
                        <span className="terminal-log-zone breach">
                          {isTamper ? 'BLOCKED' : '⚠ IN ZONE'}
                        </span>
                      ) : isPlate ? (
                        <span className="terminal-log-zone safe" style={{ borderColor: 'rgba(56, 189, 248, 0.4)', color: '#38bdf8' }}>
                          ✓ ANPR
                        </span>
                      ) : (
                        <span className="terminal-log-zone safe">
                          ✓ SAFE
                        </span>
                      )}
                    </div>
                  );
                }
              })
            )
          )}
        </div>
      </div>
    </div>
  );
}
