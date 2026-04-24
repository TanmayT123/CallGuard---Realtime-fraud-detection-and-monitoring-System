import React, { useState, useRef, useEffect } from 'react';
import AlertTimeline from './AlertTimeline';
import './DemoCall.css';

function DemoCall() {
  const [isRecording, setIsRecording] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [transcript, setTranscript] = useState('');
  const [riskScore, setRiskScore] = useState(null);
  const [detectionResult, setDetectionResult] = useState(null);
  const [tier1Details, setTier1Details] = useState(null);
  const [status, setStatus] = useState('Ready to start demo call');
  const [latestCallId, setLatestCallId] = useState(null);
  const [showTimeline, setShowTimeline] = useState(false);
  
  const wsRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioChunksRef = useRef([]);
  const fileInputRef = useRef(null);

  const startDemoCall = async () => {
    console.log('🚀 START DEMO CALL CLICKED!');
    try {
      console.log('Resetting state...');
      // Reset state
      setTranscript('');
      setRiskScore(null);
      setDetectionResult(null);
      setTier1Details(null);
      
      console.log('Setting isRecording to true...');
      // UPDATE STATE IMMEDIATELY
      setIsRecording(true);
      setStatus('🎤 Requesting microphone access...');
      
      console.log('Requesting microphone permission...');
      // Get microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true
        } 
      });
      streamRef.current = stream;
      console.log('✅ Microphone access granted');

      setStatus('🔗 Connecting to fraud detection...');
      console.log('Creating WebSocket connection to ws://localhost:8000/ws/demo-call');

      // Connect to backend WebSocket
      const ws = new WebSocket('ws://localhost:8000/ws/demo-call');
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket opened, starting recording...');
        setStatus('🎤 Recording... Speak fraud keywords, then click Stop to analyze');
        
        // Start recording
        const mediaRecorder = new MediaRecorder(stream, {
          mimeType: 'audio/webm'
        });
        mediaRecorderRef.current = mediaRecorder;
        audioChunksRef.current = [];

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            // Collect audio chunks
            audioChunksRef.current.push(event.data);
            console.log(`Chunk collected: ${event.data.size} bytes`);
          }
        };

        mediaRecorder.onstop = () => {
          console.log('MediaRecorder stopped, sending audio...');
          // Send complete audio when recording stops
          if (audioChunksRef.current.length > 0 && ws.readyState === WebSocket.OPEN) {
            const completeBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
            completeBlob.arrayBuffer().then(buffer => {
              console.log(`Sending complete audio: ${buffer.byteLength} bytes`);
              ws.send(buffer);
              setStatus('⏳ Audio sent. Waiting for transcription and fraud analysis...');
            });
          } else {
            setStatus('❌ No audio captured. Please try again and speak for a few seconds.');
            setIsAnalyzing(false);
          }
        };

        // Start collecting audio chunks every second
        mediaRecorder.start(1000);
        console.log('MediaRecorder started');
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Received from backend:', data);

        if (data.event === 'transcript') {
          setTranscript(data.text);
          setStatus('✅ Transcript received');
        } else if (data.event === 'connected') {
          if (data.call_id) {
            setLatestCallId(data.call_id);
            setShowTimeline(false);
          }
        } else if (data.event === 'detection') {
          setRiskScore(data.risk_score);
          setDetectionResult(data);
          setTier1Details({
            matched_keywords: data.matched_keywords || [],
            matched_pattern: data.matched_pattern || null
          });
          setStatus(`Risk Score: ${data.risk_score}/100`);
        } else if (data.event === 'alert') {
          setStatus('🚨 FRAUD DETECTED!');
          setDetectionResult(data);
          setIsAnalyzing(false);
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            setTimeout(() => wsRef.current.close(), 600);
          }
        } else if (data.event === 'info') {
          setStatus(`ℹ️ ${data.message}`);
          setIsAnalyzing(false);
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            setTimeout(() => wsRef.current.close(), 600);
          }
        } else if (data.event === 'error') {
          setStatus(`❌ Error: ${data.message}`);
          setIsAnalyzing(false);
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            setTimeout(() => wsRef.current.close(), 600);
          }
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        console.error('WebSocket readyState:', ws.readyState);
        setStatus(`❌ Connection failed. Check backend is running on port 8000`);
        setIsRecording(false);
        setIsAnalyzing(false);
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
          mediaRecorderRef.current.stop();
        }
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(track => track.stop());
        }
      };

      ws.onclose = (event) => {
        console.log('WebSocket closed - Code:', event.code, 'Reason:', event.reason, 'Clean:', event.wasClean);
        if (!event.wasClean) {
          setStatus(`❌ Connection error (code ${event.code})`);
          setIsRecording(false);
          setIsAnalyzing(false);
        } else if (isAnalyzing) {
          setStatus('✅ Analysis complete');
        }
        setIsRecording(false);
        setIsAnalyzing(false);
      };

    } catch (error) {
      console.error('Error starting demo call:', error);
      setStatus(`❌ Failed: ${error.message}`);
      setIsRecording(false);
      
      // Clean up if error occurs
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    }
  };

  const stopDemoCall = () => {
    setStatus('⏳ Finalizing recording and preparing analysis...');
    setIsAnalyzing(true);
    
    // Stop media recorder (this triggers onstop which sends audio)
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }

    // Stop audio stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
    }

    setIsRecording(false);
  };

  useEffect(() => {
    // Cleanup on unmount only
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const resetDemo = () => {
    setTranscript('');
    setRiskScore(null);
    setDetectionResult(null);
    setTier1Details(null);
    setSelectedFile(null);
    setLatestCallId(null);
    setShowTimeline(false);
    setIsAnalyzing(false);
    setStatus('Ready to start demo call');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const onFileSelected = (event) => {
    const file = event.target.files && event.target.files[0] ? event.target.files[0] : null;
    setSelectedFile(file);
  };

  const analyzeUploadedRecording = async () => {
    if (!selectedFile) {
      setStatus('❌ Please choose an audio file first');
      return;
    }

    try {
      setIsUploading(true);
      setTranscript('');
      setRiskScore(null);
      setDetectionResult(null);
      setTier1Details(null);
      setStatus('📤 Uploading and analyzing recording...');

      const formData = new FormData();
      formData.append('audio_file', selectedFile);

      const response = await fetch('http://localhost:8000/api/demo/upload-audio', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Failed to analyze uploaded recording');
      }

      setTranscript(data.transcript || '');
      setRiskScore(data.risk_score ?? null);
      setTier1Details(data.tier1_details || null);

      if (data.alert_generated && data.alert) {
        setDetectionResult(data.alert);
        setStatus('🚨 FRAUD DETECTED from uploaded recording!');
      } else {
        setDetectionResult(null);
        setStatus(`✅ Analysis complete. Risk score: ${data.risk_score}/100`);
      }

      if (data.call_id) {
        setLatestCallId(data.call_id);
        setShowTimeline(true);
      }
    } catch (error) {
      console.error('Upload analysis failed:', error);
      setStatus(`❌ Upload failed: ${error.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  // Debug log
  console.log('DemoCall render - isRecording:', isRecording, 'status:', status);

  return (
    <div className="demo-call">
      <div className="demo-header">
        <h2>🎙️ Demo Call - Test Fraud Detection</h2>
        <p className="demo-subtitle">
          Click Start, speak fraud keywords (IRS, taxes, arrest warrant, etc.), then click Stop to analyze
        </p>
      </div>

      <div className="demo-status">
        <div className={`status-indicator ${isRecording ? 'recording' : ''}`}>
          {isRecording && <span className="pulse"></span>}
        </div>
        <div className="status-text">{status}</div>
      </div>

      <div className="demo-controls">
        {!isRecording ? (
          <button onClick={startDemoCall} className="btn-start" disabled={isUploading || isAnalyzing}>
            {isAnalyzing ? '⏳ Analyzing...' : '🎤 Start Demo Call'}
          </button>
        ) : (
          <button onClick={stopDemoCall} className="btn-stop">
            🛑 Stop & Analyze
          </button>
        )}
        {(transcript || selectedFile) && (
          <button onClick={resetDemo} className="btn-reset">
            🔄 Reset
          </button>
        )}
        {latestCallId && !showTimeline && (
          <button onClick={() => setShowTimeline(true)} className="btn-timeline">
            🧭 View Audit Timeline
          </button>
        )}
      </div>

      <div className="upload-section">
        <h3>📁 Upload Call Recording (Recommended for Demo)</h3>
        <p className="upload-subtitle">
          If microphone is noisy or blocked, upload a recorded audio file and run the same fraud detection pipeline.
        </p>
        <div className="upload-controls">
          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*,.wav,.mp3,.m4a,.webm,.ogg"
            onChange={onFileSelected}
            disabled={isRecording || isUploading || isAnalyzing}
          />
          <button
            onClick={analyzeUploadedRecording}
            className="btn-upload"
            disabled={!selectedFile || isRecording || isUploading || isAnalyzing}
          >
            {isUploading ? '⏳ Analyzing...' : '📤 Upload & Analyze'}
          </button>
        </div>
        {selectedFile && (
          <p className="selected-file">Selected: {selectedFile.name}</p>
        )}
      </div>

      {/* Speech Transcript (Live + Upload) */}
      <div className="demo-section live-transcript">
        <h3>🎤 Speech Transcript (Live + Upload)</h3>
        <div className="transcript-box live">
          {transcript ? (
            <span className="transcript-text">{transcript}</span>
          ) : isRecording ? (
            <span className="listening">Listening... Speak now!</span>
          ) : isUploading ? (
            <span className="listening">Processing uploaded audio...</span>
          ) : selectedFile ? (
            <span className="placeholder">File selected. Click Upload & Analyze to generate transcript.</span>
          ) : (
            <span className="placeholder">Press Start Demo Call or upload a file to begin.</span>
          )}
        </div>
      </div>

      {riskScore !== null && (
        <div className="demo-section">
          <h3>⚠️ Fraud Risk Score</h3>
          <div className={`risk-display ${riskScore >= 75 ? 'high' : riskScore >= 50 ? 'medium' : 'low'}`}>
            <div className="risk-score">{riskScore}/100</div>
            <div className="risk-level">
              {riskScore >= 75 && '🚨 HIGH RISK - Likely Scam'}
              {riskScore >= 50 && riskScore < 75 && '⚠️ MEDIUM RISK - Suspicious'}
              {riskScore < 50 && '✅ LOW RISK - Seems Safe'}
            </div>
          </div>
        </div>
      )}

      {tier1Details && (tier1Details.matched_keywords?.length > 0 || tier1Details.matched_pattern) && (
        <div className="demo-section">
          <h3>🔍 Detection Details</h3>
          <div className="detection-details">
            {tier1Details.matched_keywords?.length > 0 && (
              <div className="detail-item">
                <strong>Detected Keywords:</strong>
                <div className="keywords-list">
                  {tier1Details.matched_keywords.map((kw, i) => (
                    <span key={i} className="keyword-tag">
                      {kw[0]} ({kw[1]} pts)
                    </span>
                  ))}
                </div>
              </div>
            )}
            {tier1Details.matched_pattern && (
              <div className="detail-item">
                <strong>Matched Pattern:</strong> {tier1Details.matched_pattern.name}
                <p className="pattern-desc">{tier1Details.matched_pattern.description}</p>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="demo-tips">
        <h4>💡 Try saying these to trigger fraud detection:</h4>
        <ul>
          <li>"This is the IRS calling about your taxes"</li>
          <li>"Your social security number has been suspended"</li>
          <li>"Send us a gift card immediately"</li>
          <li>"Your computer has a virus, we need remote access"</li>
          <li>"Verify your bank account information"</li>
        </ul>
      </div>

      {latestCallId && showTimeline && (
        <AlertTimeline
          callId={latestCallId}
          onClose={() => setShowTimeline(false)}
        />
      )}
    </div>
  );
}

export default DemoCall;
