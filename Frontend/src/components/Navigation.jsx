import React from 'react';
import './Navigation.css';

function Navigation({ activeTab, onTabChange, isConnected }) {
  return (
    <nav className="navbar">
      <div className="navbar-container">
        <div className="navbar-brand">
          <div className="logo">
            <span className="logo-icon">🛡️</span>
            <h1>Fraud Shield</h1>
          </div>
          <span className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? '●' : '○'} Live
          </span>
        </div>

        <div className="navbar-menu">
          <button
            className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => onTabChange('dashboard')}
          >
            📊 Dashboard
          </button>
          <button
            className={`nav-tab ${activeTab === 'demo' ? 'active' : ''}`}
            onClick={() => onTabChange('demo')}
          >
            🎙️ Demo Call
          </button>
          <button
            className={`nav-tab ${activeTab === 'monitoring' ? 'active' : ''}`}
            onClick={() => onTabChange('monitoring')}
          >
            📞 Monitoring
          </button>
          <button
            className={`nav-tab ${activeTab === 'alerts' ? 'active' : ''}`}
            onClick={() => onTabChange('alerts')}
          >
            ⚠️ Alerts
          </button>
        </div>
      </div>
    </nav>
  );
}

export default Navigation;
