// DetectionLogPanel.jsx
// Detection Log Stream Terminal — Obsidian Surveillance & Precision Video Telemetry.

import { useRef, useEffect } from 'react';

export default function DetectionLogPanel({ log = [], onClear }) {
  const listRef = useRef(null);

  // Auto-scroll to top when new entries arrive (newest is at top)
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = 0;
    }
  }, [log.length]);

  return (
    <div className="telemetry-terminal-card">
      {/* Terminal Header */}
      <div className="telemetry-terminal-header">
        <div className="telemetry-terminal-title">
          <span>&gt;_</span>
          <span>DETECTION LOG STREAM</span>
        </div>

        <div className="telemetry-terminal-actions">
          <span className="pill-count-tag entries">
            {log.length} ENTRIES
          </span>
          <button
            id="btn-clear-detection-log"
            type="button"
            className="btn-terminal-clear"
            onClick={onClear}
            title="Clear all detection logs"
          >
            <span>⊘</span> Clear
          </button>
        </div>
      </div>

      {/* Terminal Stream Console Body */}
      <div ref={listRef} className="telemetry-terminal-body">
        {log.length === 0 ? (
          <div className="terminal-prompt-line">
            <span className="prompt-prefix teal">root@sih-soc:~#</span>
            <span className="prompt-message">stream active — waiting for object detections...</span>
            <span className="blinking-caret teal" />
          </div>
        ) : (
          log.map(entry => {
            const confPct = Math.round(entry.confidence * 100);

            return (
              <div key={entry.id} className="terminal-log-row">
                {/* Timestamp */}
                <span className="terminal-log-time">[{entry.time}]</span>

                {/* Event tag */}
                <span className="terminal-log-tag detect">DETECT</span>

                {/* Object name */}
                <span className="terminal-log-label">
                  {entry.label}
                </span>

                {/* Confidence */}
                <span className="terminal-log-conf">
                  {confPct}%
                </span>

                {/* Zone status tag */}
                {entry.intruding ? (
                  <span className="terminal-log-zone breach">
                    ⚠ IN ZONE
                  </span>
                ) : (
                  <span className="terminal-log-zone safe">
                    ✓ SAFE
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}


