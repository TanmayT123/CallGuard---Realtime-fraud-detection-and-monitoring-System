import React, { useState, useEffect } from 'react';
import AlertNotification from './components/AlertNotification';
import AlertTimeline from './components/AlertTimeline';
import CallMonitor from './components/CallMonitor';
import Dashboard from './components/Dashboard';
import DemoCall from './components/DemoCall';
import Navigation from './components/Navigation';
import './App.css';

function App() {
  const [alerts, setAlerts] = useState([]);
  const [currentCall] = useState(null);
  const [stats, setStats] = useState(null);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isConnected, setIsConnected] = useState(false);
  const [timelineCallId, setTimelineCallId] = useState(null);

  // Setup alert fetching (REST polling)
  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/alerts?limit=50');
        const data = await response.json();
        console.log('Fetched alerts:', data);  // Debug
        setAlerts(data.alerts || []);
        setIsConnected(true);
      } catch (e) {
        console.error('Failed to fetch alerts:', e);
        setIsConnected(false);
      }
    };

    fetchAlerts();
    // Refresh alerts every 5 seconds for real-time effect
    const interval = setInterval(fetchAlerts, 5000);
    return () => clearInterval(interval);
  }, []);

  // Fetch statistics
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/statistics');
        const data = await response.json();
        setStats(data);
      } catch (e) {
        console.error('Failed to fetch stats:', e);
      }
    };

    fetchStats();
    // Refresh stats every 30 seconds
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="App">
      <Navigation 
        activeTab={activeTab} 
        onTabChange={setActiveTab}
        isConnected={isConnected}
      />
      
      <main className="main-content">
        {activeTab === 'dashboard' && (
          <Dashboard stats={stats} recentAlerts={alerts.slice(0, 10)} />
        )}

        {activeTab === 'demo' && (
          <DemoCall />
        )}

        {activeTab === 'monitoring' && (
          <CallMonitor currentCall={currentCall} />
        )}

        {activeTab === 'alerts' && (
          <div className="alerts-page">
            <h1>Recent Alerts</h1>
            <div className="alerts-list">
              {alerts.length > 0 ? (
                alerts.map((alert, idx) => (
                  <AlertNotification
                    key={idx}
                    alert={alert}
                    onViewTimeline={(callId) => setTimelineCallId(callId)}
                    isTimelineOpen={timelineCallId === alert.call_id}
                  />
                ))
              ) : (
                <div className="no-alerts">
                  <p>No alerts yet. System is monitoring.</p>
                </div>
              )}
            </div>

            {timelineCallId && (
              <AlertTimeline
                callId={timelineCallId}
                onClose={() => setTimelineCallId(null)}
              />
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
