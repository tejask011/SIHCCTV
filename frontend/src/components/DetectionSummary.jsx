// DetectionSummary.jsx
// Real-Time Detection Summary with Circular Radar Graphic and Precision Metric Tiles.

import { useState } from 'react';

const GROUP_META = {
  HUMAN:        { icon: '🧍', color: 'var(--human)'   },
  ANIMAL:       { icon: '🐾', color: 'var(--animal)'  },
  VEHICLE:      { icon: '🚗', color: 'var(--vehicle)' },
  OBJECT:       { icon: '📦', color: 'var(--object)'  },
  'NO. PLATES': { icon: '🚘', color: '#38bdf8'        },
};

const DEFAULT_META = { icon: '🔍', color: 'var(--on-surface-variant)' };

export default function DetectionSummary({ summary = {}, activeIntrusion = false }) {
  const [collapsed, setCollapsed] = useState({});

  const groups = Object.entries(summary || {});

  // Calculate metrics
  let personCount = 0;
  let wearableCount = 0;
  let totalCount = 0;

  groups.forEach(([cat, labels]) => {
    Object.entries(labels || {}).forEach(([lbl, cnt]) => {
      totalCount += cnt;
      if (cat === 'HUMAN') personCount += cnt;
      if (['backpack', 'handbag', 'tie', 'suitcase', 'umbrella', 'cell phone', 'watch'].includes(lbl.toLowerCase())) {
        wearableCount += cnt;
      }
    });
  });

  const threatCount = activeIntrusion ? 1 : 0;

  function toggleGroup(cat) {
    setCollapsed(prev => ({ ...prev, [cat]: !prev[cat] }));
  }

  return (
    <div className="panel-chassis">
      {/* ── Card Header ── */}
      <div className="panel-chassis-header">
        <div className="panel-header-title">
          <span className="status-dot-led" style={{ color: 'var(--secondary)' }} />
          <span>REAL-TIME DETECTION SUMMARY</span>
        </div>
        <span className="badge-tag-sm">AI Tracker 1.0</span>
      </div>

      {/* ── Radar Visualizer & Metrics ── */}
      <div className="radar-display-box">
        {/* Animated Circular Radar Graphic */}
        <div className="radar-art-frame">
          <div className="radar-ring-inner" />
          <div className="radar-crosshair-h" />
          <div className="radar-crosshair-v" />
          <div className="radar-sweep-beam" />
          <div className="radar-center-target" />
        </div>

        <div className="radar-status-caption">
          {totalCount > 0 ? `Tracking ${totalCount} Active Entities` : 'Awaiting telemetry stream'}
        </div>
        <div className="radar-status-sub">
          {totalCount > 0
            ? 'Neural inference active on current optical viewport'
            : 'No detections yet — connect a source to populate metrics'}
        </div>

        {/* 3 Metric Tiles */}
        <div className="metric-tiles-matrix">
          <div className="metric-tile-card">
            <span className="metric-tile-label">PERSONS</span>
            <span className="metric-tile-value">{personCount}</span>
            <span className="metric-tile-sub">Normal flow</span>
          </div>

          <div className="metric-tile-card">
            <span className="metric-tile-label">WEARABLES</span>
            <span className="metric-tile-value">{wearableCount}</span>
            <span className="metric-tile-sub muted">PPE verified</span>
          </div>

          <div className="metric-tile-card">
            <span className="metric-tile-label">THREATS</span>
            <span className={`metric-tile-value ${threatCount > 0 ? 'threat' : ''}`}>
              {threatCount}
            </span>
            <span className={`metric-tile-sub ${threatCount > 0 ? 'danger' : 'muted'}`}>
              {threatCount > 0 ? 'Breach active' : 'No violations'}
            </span>
          </div>
        </div>

        {/* Dynamic Category Details when objects are present */}
        {groups.length > 0 && (
          <div style={{ width: '100%', marginTop: 14, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {groups.map(([category, labels]) => {
              const meta = GROUP_META[category] ?? DEFAULT_META;
              const subItems = Object.entries(labels);
              const groupSum = subItems.reduce((s, [, n]) => s + n, 0);
              const isOpen = !collapsed[category];

              return (
                <div
                  key={category}
                  style={{
                    background: 'var(--surface-container-lowest)',
                    border: '1px solid var(--outline)',
                    borderLeft: `3px solid ${meta.color}`,
                    borderRadius: 'var(--radius-xs)',
                    overflow: 'hidden',
                  }}
                >
                  <button
                    type="button"
                    onClick={() => toggleGroup(category)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 14px',
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--on-surface)',
                      cursor: 'pointer',
                      fontFamily: 'var(--font-display)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 16 }}>{meta.icon}</span>
                      <span style={{ fontSize: 14.5, fontWeight: 700, letterSpacing: '0.04em', color: meta.color }}>
                        {category}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 13,
                        fontWeight: 700,
                        color: meta.color,
                        background: 'rgba(255, 255, 255, 0.05)',
                        padding: '2px 8px',
                        borderRadius: 3,
                      }}>
                        {groupSum}
                      </span>
                      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{isOpen ? '▲' : '▼'}</span>
                    </div>
                  </button>

                  {isOpen && (
                    <div style={{
                      padding: '8px 14px 10px',
                      borderTop: '1px solid var(--outline)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 4,
                    }}>
                      {subItems.map(([label, count]) => (
                        <div
                          key={label}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            fontSize: 13.5,
                            fontFamily: 'var(--font-body)',
                            color: 'var(--on-surface-variant)',
                          }}
                        >
                          <span style={{ textTransform: 'capitalize' }}>└ {label}</span>
                          <span style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: 12.5,
                            fontWeight: 600,
                            color: 'var(--on-surface)',
                          }}>
                            ×{count}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

