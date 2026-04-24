import React from 'react';
import './AlertNotification.css';

function AlertNotification({ alert, onViewTimeline, isTimelineOpen = false }) {
  if (!alert) return null;

  const getRiskColor = (level) => {
    switch (level) {
      case 'high':
        return '#dc2626';
      case 'medium':
        return '#f59e0b';
      case 'low':
        return '#10b981';
      default:
        return '#6b7280';
    }
  };

  const getRiskBgClass = (level) => {
    switch (level) {
      case 'high':
        return 'risk-high';
      case 'medium':
        return 'risk-medium';
      case 'low':
        return 'risk-low';
      default:
        return 'risk-unknown';
    }
  };

  const riskColor = getRiskColor(alert.risk_level);

  return (
    <div className={`alert-card ${getRiskBgClass(alert.risk_level)}`}>
      <div className="alert-header">
        <div className="alert-title">
          {alert.risk_level === 'high' && <span className="alert-icon">⚠️</span>}
          {alert.risk_level === 'medium' && <span className="alert-icon">⚡</span>}
          {alert.risk_level === 'low' && <span className="alert-icon">ℹ️</span>}
          <h3>{alert.message || 'Fraud Alert'}</h3>
        </div>
        <div className="alert-meta">
          <span className="risk-badge" style={{ borderColor: riskColor, color: riskColor }}>
            {alert.risk_level?.toUpperCase()}
          </span>
        </div>
      </div>

      <div className="alert-score">
        <div className="score-label">Risk Score</div>
        <div className="score-bar">
          <div
            className="score-fill"
            style={{
              width: `${alert.risk_score}%`,
              backgroundColor: riskColor
            }}
          />
        </div>
        <div className="score-value">{alert.risk_score}/100</div>
      </div>

      {alert.red_flags && alert.red_flags.length > 0 && (
        <div className="alert-flags">
          <h4>🚩 Red Flags</h4>
          <ul>
            {alert.red_flags.slice(0, 3).map((flag, idx) => (
              <li key={idx}>{flag}</li>
            ))}
          </ul>
        </div>
      )}

      {alert.recommended_action && (
        <div className="alert-action">
          <h4>⚡ Recommended Action</h4>
          <p>{alert.recommended_action}</p>
        </div>
      )}

      <div className="alert-footer">
        <span className="alert-tier">
          {alert.detection_tier === 'tier1' ? '⚡ Fast Detection' : '🤖 AI Analysis'}
        </span>
        <div className="alert-footer-actions">
          {onViewTimeline && alert.call_id && (
            <button
              className={`timeline-btn ${isTimelineOpen ? 'open' : ''}`}
              onClick={() => onViewTimeline(alert.call_id)}
            >
              {isTimelineOpen ? 'Timeline Open' : 'View Audit Timeline'}
            </button>
          )}
          <span className="alert-time">
            {new Date(alert.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </div>
    </div>
  );
}

export default AlertNotification;
