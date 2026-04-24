import React from 'react';
import './Dashboard.css';

function Dashboard({ stats, recentAlerts }) {
  return (
    <div className="dashboard">
      <h1>🛡️ Fraud Detection Dashboard</h1>

      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon">📞</div>
            <div className="stat-content">
              <h3>Total Calls</h3>
              <p className="stat-value">{stats.total_calls}</p>
            </div>
          </div>

          <div className="stat-card high-risk">
            <div className="stat-icon">⚠️</div>
            <div className="stat-content">
              <h3>Scams Detected</h3>
              <p className="stat-value">{stats.scam_calls}</p>
              <p className="stat-percentage">{stats.scam_percentage.toFixed(1)}%</p>
            </div>
          </div>

          <div className="stat-card medium-risk">
            <div className="stat-icon">⚡</div>
            <div className="stat-content">
              <h3>Medium Risk Alerts</h3>
              <p className="stat-value">{stats.medium_risk_alerts}</p>
            </div>
          </div>

          <div className="stat-card info">
            <div className="stat-icon">⏱️</div>
            <div className="stat-content">
              <h3>Avg Call Duration</h3>
              <p className="stat-value">{stats.average_call_duration}s</p>
            </div>
          </div>
        </div>
      )}

      <div className="recent-section">
        <h2>📍 Recent Alerts</h2>
        {recentAlerts && recentAlerts.length > 0 ? (
          <div className="recent-alerts">
            {recentAlerts.map((alert, idx) => (
              <div key={idx} className="recent-item">
                <div className="recent-time">
                  {new Date(alert.timestamp).toLocaleTimeString()}
                </div>
                <div className="recent-content">
                  <div className="recent-message">{alert.message}</div>
                  <div className="recent-details">
                    {alert.details?.caller_id && (
                      <span>Caller: {alert.details.caller_id}</span>
                    )}
                  </div>
                </div>
                <div className={`recent-badge ${alert.risk_level}`}>
                  {alert.risk_score}/100
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <p>No recent alerts. System is monitoring...</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
