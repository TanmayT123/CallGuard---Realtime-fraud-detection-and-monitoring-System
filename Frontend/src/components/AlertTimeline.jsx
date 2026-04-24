import React, { useEffect, useMemo, useState } from 'react';
import './AlertTimeline.css';

function AlertTimeline({ callId, onClose }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [callDetail, setCallDetail] = useState(null);
  const [detectionLogs, setDetectionLogs] = useState([]);

  useEffect(() => {
    if (!callId) return;

    const fetchTimelineData = async () => {
      setLoading(true);
      setError(null);

      try {
        const [callRes, logsRes] = await Promise.allSettled([
          fetch(`http://localhost:8000/api/calls/${encodeURIComponent(callId)}`),
          fetch(`http://localhost:8000/api/detection-logs?call_id=${encodeURIComponent(callId)}&limit=100`)
        ]);

        if (callRes.status === 'fulfilled' && callRes.value.ok) {
          const callJson = await callRes.value.json();
          setCallDetail(callJson);
        } else {
          setCallDetail(null);
        }

        if (logsRes.status === 'fulfilled' && logsRes.value.ok) {
          const logsJson = await logsRes.value.json();
          setDetectionLogs(logsJson.logs || []);
        } else {
          setDetectionLogs([]);
        }
      } catch (e) {
        setError('Failed to load audit timeline data.');
      } finally {
        setLoading(false);
      }
    };

    fetchTimelineData();
  }, [callId]);

  const timelineEvents = useMemo(() => {
    const events = [];

    if (callDetail?.start_time) {
      events.push({
        key: `call-start-${callId}`,
        type: 'call_started',
        timestamp: callDetail.start_time,
        title: 'Call started',
        detail: `Caller: ${callDetail.caller_id || 'Unknown'} | Number: ${callDetail.phone_number || 'Unknown'}`
      });
    }

    (callDetail?.transcripts || []).forEach((t, idx) => {
      events.push({
        key: `transcript-${idx}`,
        type: 'transcript',
        timestamp: t.timestamp,
        title: 'Transcript chunk',
        detail: (t.text || '').slice(0, 220) || 'Transcript text unavailable'
      });
    });

    (detectionLogs || []).forEach((log, idx) => {
      const tier2Text = log.tier2_triggered
        ? `Tier2=${log.tier2_score ?? 'n/a'}`
        : 'Tier2 not triggered';

      events.push({
        key: `score-${idx}`,
        type: 'score_update',
        timestamp: log.timestamp,
        title: 'Score update',
        detail: `Tier1=${log.tier1_score ?? 'n/a'} | ${tier2Text}`
      });
    });

    (callDetail?.alerts || []).forEach((a, idx) => {
      events.push({
        key: `alert-${idx}`,
        type: 'alert_fired',
        timestamp: a.timestamp,
        title: 'Alert fired',
        detail: `${a.risk_level?.toUpperCase() || 'UNKNOWN'} risk (${a.risk_score ?? 'n/a'}/100) | ${a.message || 'Alert generated'}`
      });
    });

    if (callDetail?.end_time) {
      events.push({
        key: `call-end-${callId}`,
        type: 'call_ended',
        timestamp: callDetail.end_time,
        title: 'Call ended',
        detail: `Duration: ${callDetail.duration_seconds ?? 0}s | Final risk: ${callDetail.risk_level || 'n/a'}`
      });
    }

    return events
      .filter((e) => !!e.timestamp)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  }, [callDetail, detectionLogs, callId]);

  const eventClass = (type) => {
    switch (type) {
      case 'call_started':
        return 'event-call-started';
      case 'transcript':
        return 'event-transcript';
      case 'score_update':
        return 'event-score';
      case 'alert_fired':
        return 'event-alert';
      case 'call_ended':
        return 'event-call-ended';
      default:
        return '';
    }
  };

  return (
    <section className="alert-timeline">
      <div className="timeline-header">
        <div>
          <h2>Alert Audit Timeline</h2>
          <p>Call ID: {callId}</p>
        </div>
        <button className="timeline-close" onClick={onClose}>Close</button>
      </div>

      {loading && <div className="timeline-state">Loading timeline...</div>}
      {error && <div className="timeline-state error">{error}</div>}

      {!loading && !error && timelineEvents.length === 0 && (
        <div className="timeline-state">No timeline events found for this call.</div>
      )}

      {!loading && !error && timelineEvents.length > 0 && (
        <div className="timeline-list">
          {timelineEvents.map((event) => (
            <article key={event.key} className={`timeline-item ${eventClass(event.type)}`}>
              <div className="timeline-dot" />
              <div className="timeline-content">
                <div className="timeline-meta">
                  <span className="timeline-title">{event.title}</span>
                  <span className="timeline-time">{new Date(event.timestamp).toLocaleString()}</span>
                </div>
                <p>{event.detail}</p>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export default AlertTimeline;
