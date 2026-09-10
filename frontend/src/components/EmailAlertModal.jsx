// EmailAlertModal.jsx
// Interactive UI modal for configuring automated intrusion email dispatch with photo snapshot.

import { useState, useEffect } from 'react';
import { API } from '../config';

export default function EmailAlertModal({ isOpen, onClose, emailStatus = {} }) {
  const [enabled, setEnabled] = useState(false);
  const [recipientEmail, setRecipientEmail] = useState('');
  const [senderEmail, setSenderEmail] = useState('');
  const [appPassword, setAppPassword] = useState('');
  const [smtpServer, setSmtpServer] = useState('smtp.gmail.com');
  const [smtpPort, setSmtpPort] = useState(587);
  const [cooldownSec, setCooldownSec] = useState(45);

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [feedback, setFeedback] = useState(null); // { type: 'success' | 'error', text: string }

  // Load initial settings from backend
  useEffect(() => {
    if (isOpen) {
      fetch(`${API}/api/notifications/config`)
        .then(res => res.json())
        .then(data => {
          if (data.ok && data.config) {
            const c = data.config;
            setEnabled(c.enabled || false);
            setRecipientEmail(c.recipient_email || '');
            setSenderEmail(c.sender_email || '');
            setSmtpServer(c.smtp_server || 'smtp.gmail.com');
            setSmtpPort(c.smtp_port || 587);
            setCooldownSec(c.cooldown_sec || 45);
          }
        })
        .catch(() => {});
      setFeedback(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  async function handleSave(e) {
    if (e) e.preventDefault();
    setIsSaving(true);
    setFeedback(null);
    try {
      const res = await fetch(`${API}/api/notifications/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled,
          recipient_email: recipientEmail,
          sender_email: senderEmail,
          app_password: appPassword,
          smtp_server: smtpServer,
          smtp_port: parseInt(smtpPort, 10) || 587,
          cooldown_sec: parseInt(cooldownSec, 10) || 45,
        })
      });
      const data = await res.json();
      if (data.ok) {
        setFeedback({ type: 'success', text: 'Email notification settings saved successfully!' });
      } else {
        setFeedback({ type: 'error', text: data.error || 'Failed to save settings' });
      }
    } catch (err) {
      setFeedback({ type: 'error', text: 'Network error communicating with backend' });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTestEmail() {
    if (!recipientEmail.trim()) {
      setFeedback({ type: 'error', text: 'Please enter a recipient email address first.' });
      return;
    }
    // Save first to ensure latest credentials are used
    await handleSave();
    setIsTesting(true);
    setFeedback(null);
    try {
      const res = await fetch(`${API}/api/notifications/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipient_email: recipientEmail })
      });
      const data = await res.json();
      if (data.ok) {
        setFeedback({ type: 'success', text: `✓ Test alert dispatched to ${recipientEmail}!` });
      } else {
        setFeedback({ type: 'error', text: `Test failed: ${data.error}` });
      }
    } catch (err) {
      setFeedback({ type: 'error', text: 'Network error dispatching test email' });
    } finally {
      setIsTesting(false);
    }
  }

  return (
    <div className="modal-backdrop" style={{
      position: 'fixed',
      top: 0,
      left: 0,
      width: '100vw',
      height: '100vh',
      background: 'rgba(5, 7, 10, 0.78)',
      backdropFilter: 'blur(6px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      padding: 16
    }}>
      <div className="modal-card" style={{
        background: 'var(--surface-container)',
        border: '1px solid var(--outline)',
        borderTop: '3px solid var(--primary)',
        borderRadius: 'var(--radius-sm)',
        width: '100%',
        maxWidth: 540,
        boxShadow: '0 12px 40px rgba(0, 0, 0, 0.65)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        animation: 'fadeIn 0.2s ease-out'
      }}>
        {/* Modal Header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid var(--outline)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 22 }}>📧</span>
            <div>
              <div style={{
                fontFamily: 'var(--font-display)',
                fontSize: 15,
                fontWeight: 800,
                letterSpacing: '0.04em',
                color: 'var(--on-surface)'
              }}>
                AUTOMATED INTRUSION EMAIL DISPATCH
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
                Annotated photo snapshot + incident telemetry log
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              fontSize: 20,
              cursor: 'pointer',
              padding: '4px 8px',
              borderRadius: 4
            }}
          >
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSave} style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Dispatch Activation Switch */}
          <div style={{
            background: enabled ? 'rgba(16, 185, 129, 0.12)' : 'var(--surface-container-low)',
            border: `1px solid ${enabled ? 'var(--secondary)' : 'var(--outline)'}`,
            borderRadius: 'var(--radius-xs)',
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 700, color: enabled ? 'var(--secondary)' : 'var(--on-surface)' }}>
                {enabled ? 'AUTOMATIC EMAIL DISPATCH: ACTIVE' : 'AUTOMATIC EMAIL DISPATCH: DISABLED'}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                Instantly emails snapshot &amp; logs when boundary is breached (&gt;5s)
              </div>
            </div>

            <label className="toggle-switch" style={{ position: 'relative', display: 'inline-block', width: 44, height: 24, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={enabled}
                onChange={e => setEnabled(e.target.checked)}
                style={{ opacity: 0, width: 0, height: 0 }}
              />
              <span style={{
                position: 'absolute',
                cursor: 'pointer',
                top: 0, left: 0, right: 0, bottom: 0,
                backgroundColor: enabled ? 'var(--secondary)' : '#334155',
                borderRadius: 24,
                transition: '0.3s'
              }}>
                <span style={{
                  position: 'absolute',
                  content: '',
                  height: 18,
                  width: 18,
                  left: enabled ? 23 : 3,
                  bottom: 3,
                  backgroundColor: '#ffffff',
                  borderRadius: '50%',
                  transition: '0.3s'
                }} />
              </span>
            </label>
          </div>

          {/* Recipient Email Address Input */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, fontWeight: 700, color: 'var(--primary)' }}>
              RECIPIENT EMAIL ADDRESS (WHERE TO SEND ALERTS)
            </label>
            <input
              type="email"
              placeholder="e.g. security-officer@agency.gov.in"
              value={recipientEmail}
              onChange={e => setRecipientEmail(e.target.value)}
              required={enabled}
              style={{
                background: 'var(--surface-container-lowest)',
                border: '1px solid var(--outline)',
                borderRadius: 'var(--radius-xs)',
                padding: '10px 14px',
                color: 'var(--on-surface)',
                fontFamily: 'var(--font-mono)',
                fontSize: 13.5,
                outline: 'none'
              }}
            />
          </div>

          {/* Anti-Spam Cooldown */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
                ANTI-SPAM DISPATCH COOLDOWN
              </label>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--primary)', fontWeight: 700 }}>
                {cooldownSec} Seconds
              </span>
            </div>
            <input
              type="range"
              min="15"
              max="180"
              step="5"
              value={cooldownSec}
              onChange={e => setCooldownSec(parseInt(e.target.value, 10))}
              style={{ accentColor: 'var(--primary)', cursor: 'pointer' }}
            />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
              Prevents duplicate emails if an intruder lingers in the restricted zone.
            </span>
          </div>

          {/* Collapsible SMTP Sender Credentials */}
          <div style={{
            border: '1px solid var(--outline)',
            borderRadius: 'var(--radius-xs)',
            overflow: 'hidden'
          }}>
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              style={{
                width: '100%',
                background: 'var(--surface-container-low)',
                border: 'none',
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                color: 'var(--on-surface-variant)',
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
                fontSize: 12.5
              }}
            >
              <span>⚙ SMTP Sender Settings (Optional / Gmail App Password)</span>
              <span>{showAdvanced ? '▲' : '▼'}</span>
            </button>

            {showAdvanced && (
              <div style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: 12, background: 'var(--surface-container-lowest)' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <label style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-muted)' }}>
                    Sender Email (Gmail)
                  </label>
                  <input
                    type="email"
                    placeholder="your-bot@gmail.com"
                    value={senderEmail}
                    onChange={e => setSenderEmail(e.target.value)}
                    style={{
                      background: 'var(--surface-container)',
                      border: '1px solid var(--outline)',
                      borderRadius: 3,
                      padding: '7px 10px',
                      color: 'var(--on-surface)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 12
                    }}
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <label style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-muted)' }}>
                    Gmail 16-Letter App Password
                  </label>
                  <input
                    type="password"
                    placeholder="xxxx xxxx xxxx xxxx"
                    value={appPassword}
                    onChange={e => setAppPassword(e.target.value)}
                    style={{
                      background: 'var(--surface-container)',
                      border: '1px solid var(--outline)',
                      borderRadius: 3,
                      padding: '7px 10px',
                      color: 'var(--on-surface)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 12
                    }}
                  />
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--text-muted)' }}>
                    Tip: Google Account &rarr; Security &rarr; 2-Step Verification &rarr; App Passwords. If left blank, simulation mode generates full snapshots for demo.
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Feedback message */}
          {feedback && (
            <div style={{
              padding: '8px 12px',
              borderRadius: 'var(--radius-xs)',
              background: feedback.type === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
              border: `1px solid ${feedback.type === 'success' ? 'var(--secondary)' : 'var(--error)'}`,
              color: feedback.type === 'success' ? '#6ee7b7' : '#fca5a5',
              fontFamily: 'var(--font-mono)',
              fontSize: 12.5
            }}>
              {feedback.text}
            </div>
          )}

          {/* Modal Actions */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 6, gap: 10 }}>
            <button
              type="button"
              onClick={handleTestEmail}
              disabled={isTesting || isSaving}
              style={{
                background: 'rgba(245, 158, 11, 0.12)',
                border: '1px solid var(--primary)',
                color: 'var(--primary)',
                padding: '9px 14px',
                borderRadius: 'var(--radius-xs)',
                fontFamily: 'var(--font-mono)',
                fontSize: 12.5,
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6
              }}
            >
              <span>{isTesting ? '⏳' : '🚀'}</span>
              <span>{isTesting ? 'Sending...' : 'Send Test Alert'}</span>
            </button>

            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                onClick={onClose}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--outline)',
                  color: 'var(--text-muted)',
                  padding: '9px 14px',
                  borderRadius: 'var(--radius-xs)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12.5,
                  cursor: 'pointer'
                }}
              >
                Close
              </button>
              <button
                type="submit"
                disabled={isSaving}
                style={{
                  background: 'var(--primary)',
                  border: 'none',
                  color: '#000000',
                  padding: '9px 18px',
                  borderRadius: 'var(--radius-xs)',
                  fontFamily: 'var(--font-display)',
                  fontSize: 13,
                  fontWeight: 800,
                  letterSpacing: '0.04em',
                  cursor: 'pointer'
                }}
              >
                {isSaving ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
