import React from 'react';
import './CallMonitor.css';

function CallMonitor({ currentCall }) {
  if (!currentCall) {
    return (
      <div className="call-monitor">
        <div className="monitor-placeholder">
          <p>Waiting for incoming calls...</p>
          <p className="placeholder-icon">📞</p>
        </div>
      </div>
    );
  }

  return (
    <div className="call-monitor">
      <div className="monitor-header">
        <h1>Current Call Monitoring</h1>
        <span className="monitor-status live">● LIVE</span>
      </div>

      <div className="monitor-content">
        <div className="call-info">
          <div className="info-item">
            <label>Caller ID</label>
            <p>{currentCall.details?.caller_id || 'Unknown'}</p>
          </div>
          <div className="info-item">
            <label>Call Duration</label>
            <p>{currentCall.details?.duration || 0}s</p>
          </div>
        </div>

        <div className="risk-assessment">
          <h2>Risk Assessment</h2>
          <div className="risk-score-large">
            <div className="score-circle" style={{
              borderColor: currentCall.risk_level === 'high' ? '#dc2626' : 
                           currentCall.risk_level === 'medium' ? '#f59e0b' : '#10b981'
            }}>
              {currentCall.risk_score}
            </div>
            <div className="score-label">
              <span className="risk-level">{currentCall.risk_level?.toUpperCase()}</span>
              <span className="score-text">Risk Score</span>
            </div>
          </div>
        </div>

        {currentCall.red_flags && currentCall.red_flags.length > 0 && (
          <div className="red-flags-section">
            <h2>🚩 Detected Red Flags</h2>
            <ul className="flags-list">
              {currentCall.red_flags.map((flag, idx) => (
                <li key={idx}>{flag}</li>
              ))}
            </ul>
          </div>
        )}

        {currentCall.recommended_action && (
          <div className="action-section">
            <h2>⚡ Recommended Action</h2>
            <div className="action-box">
              {currentCall.recommended_action}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default CallMonitor;
