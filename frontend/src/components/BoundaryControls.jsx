// BoundaryControls.jsx
// Boundary toolbar below video viewport — Obsidian Surveillance & Precision Video Telemetry.

export default function BoundaryControls({
  isDrawing,
  isConnected,
  pointCount,
  onStartDraw,
  onUndo,
  onFinishDraw,
  onClear,
}) {
  return (
    <div className="boundary-bar-chassis">
      <div className="boundary-bar-actions">
        {!isDrawing ? (
          <>
            <button
              id="btn-draw-boundary"
              className="btn-boundary-amber"
              onClick={onStartDraw}
              disabled={!isConnected}
              type="button"
              title="Click points on the video to define a restricted zone"
            >
              <span>☩</span> Draw Boundary
            </button>

            <button
              id="btn-clear-boundary"
              className="btn-boundary-danger"
              onClick={onClear}
              disabled={!isConnected || pointCount === 0}
              type="button"
              title="Remove boundary completely"
            >
              <span>⎚</span> Erase Boundary
            </button>

            <button
              type="button"
              className="btn-link-reset"
              onClick={onClear}
              disabled={!isConnected}
            >
              Reset ROI
            </button>
          </>
        ) : (
          <>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--primary)',
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}>
              <span className="status-dot-led" style={{ color: 'var(--primary)' }} />
              CLICK VIEWPORT ({pointCount} pts, min 3)
            </span>

            <button
              id="btn-undo-point"
              className="btn-boundary-amber"
              onClick={onUndo}
              disabled={pointCount === 0}
              type="button"
            >
              ↩ Undo
            </button>

            <button
              id="btn-finish-boundary"
              className="btn-action-connect"
              style={{ padding: '5px 12px', fontSize: 11 }}
              onClick={onFinishDraw}
              disabled={pointCount < 3}
              type="button"
            >
              ✓ Arm Boundary ({pointCount})
            </button>

            <button
              id="btn-cancel-draw"
              className="btn-boundary-danger"
              onClick={onClear}
              type="button"
            >
              ✕ Cancel
            </button>
          </>
        )}
      </div>

      <div className="boundary-preset-meta">
        PRESET: <strong style={{ color: 'var(--on-surface-variant)' }}>Default ROI Full View</strong>
      </div>
    </div>
  );
}

