"""WebSocket handler for Twilio audio streaming."""
import sys
from pathlib import Path
import logging
import base64
import json
import uuid
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.detection_service import get_detection_service
from backend.utils.redis_client import (
    set_call_session,
    get_call_session,
    delete_call_session
)
from backend.models import get_db_context
from backend.models.database import Call, Alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections per call."""

    def __init__(self):
        """Initialize connection manager."""
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, call_id: str, websocket: WebSocket):
        """Accept and register new connection."""
        await websocket.accept()
        self.active_connections[call_id] = websocket
        logger.info(f"[{call_id}] WebSocket connected")

    def disconnect(self, call_id: str):
        """Unregister disconnected connection."""
        if call_id in self.active_connections:
            del self.active_connections[call_id]
            logger.info(f"[{call_id}] WebSocket disconnected")

    async def send_personal(self, call_id: str, data: dict):
        """Send message to specific connection."""
        if call_id in self.active_connections:
            try:
                await self.active_connections[call_id].send_json(data)
            except Exception as e:
                logger.error(
                    f"[{call_id}] Failed to send WebSocket message: {e}"
                )

    def get_connection(self, call_id: str) -> Optional[WebSocket]:
        """Get connection for call."""
        return self.active_connections.get(call_id)


# Global connection manager
manager = ConnectionManager()


@router.websocket("/call/{call_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    call_id: str,
    phone_number: str = Query(default="Unknown"),
    caller_id: str = Query(default="Unknown")
):
    """
    WebSocket endpoint for Twilio audio streaming.
    
    Expects Twilio to send audio in this format:
    {
        "event": "media",
        "media": {
            "payload": "base64_encoded_mulaw_audio",
            "timestamp": "2026-02-10T10:30:00.020Z",
            "track": "inbound"
        }
    }
    
    Query Parameters:
        - phone_number: Incoming phone number
        - caller_id: Caller ID (if available)
    """
    await manager.connect(call_id, websocket)
    
    try:
        # Initialize call session in Redis
        call_session = {
            "call_id": call_id,
            "status": "active",
            "phone_number": phone_number,
            "caller_id": caller_id,
            "start_time": datetime.utcnow().isoformat(),
            "message_count": 0,
            "transcripts": [],
            "alerts": [],
            "max_risk_score": 0
        }
        
        await set_call_session(call_id, call_session, expire_seconds=3600)
        
        # Create call record in database
        with get_db_context() as db:
            db_call = Call(
                call_id=call_id,
                phone_number=phone_number,
                caller_id=caller_id,
                status="active"
            )
            db.add(db_call)
            db.commit()
        
        # Send connection confirmation
        await websocket.send_json({
            "event": "connected",
            "call_id": call_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info(
            f"[{call_id}] Call started from {phone_number} "
            f"(caller_id: {caller_id})"
        )
        
        # Get detection service
        detection_service = get_detection_service()
        
        # Main message loop
        while True:
            try:
                # Receive message from Twilio
                message = await websocket.receive_text()
                data = json.loads(message)
                
                event_type = data.get("event")
                
                if event_type == "media":
                    # Process audio chunk
                    await _handle_media_event(
                        call_id=call_id,
                        data=data,
                        detection_service=detection_service,
                        websocket=websocket
                    )
                
                elif event_type == "start":
                    # Call started (usually first event)
                    logger.debug(f"[{call_id}] Call start event received")
                
                elif event_type == "stop":
                    # Call ended
                    logger.info(f"[{call_id}] Call stop event received")
                    break
                
                elif event_type == "mark":
                    # Heartbeat/marker from Twilio
                    logger.debug(f"[{call_id}] Heartbeat received")
                
                else:
                    logger.debug(f"[{call_id}] Unknown event: {event_type}")
            
            except json.JSONDecodeError:
                logger.error(f"[{call_id}] Invalid JSON received")
            
            except WebSocketDisconnect:
                logger.info(f"[{call_id}] WebSocket disconnected")
                break
    
    except Exception as e:
        logger.error(
            f"[{call_id}] WebSocket error: {e}",
            exc_info=True
        )
    
    finally:
        # Finalize call
        await _finalize_call(call_id, detection_service)
        manager.disconnect(call_id)


async def _handle_media_event(
    call_id: str,
    data: dict,
    detection_service,
    websocket: WebSocket
):
    """
    Handle media (audio) event from Twilio.
    
    Args:
        call_id: Call identifier
        data: Event data from Twilio
        detection_service: Detection service instance
        websocket: WebSocket connection
    """
    try:
        media = data.get("media", {})
        payload = media.get("payload", "")
        timestamp = media.get("timestamp", datetime.utcnow().isoformat())
        
        # Decode base64 audio
        mulaw_bytes = base64.b64decode(payload)
        
        # Process audio chunk
        alert = await detection_service.process_audio_chunk(
            call_id=call_id,
            mulaw_bytes=mulaw_bytes,
            timestamp=timestamp
        )
        
        # If alert generated, send to client
        if alert:
            logger.warning(f"[{call_id}] Alert generated, sending to client")
            
            await websocket.send_json({
                "event": "alert",
                "data": alert
            })
            
            # Save alert to database
            try:
                with get_db_context() as db:
                    db_alert = Alert(
                        alert_id=alert['alert_id'],
                        call_id=call_id,
                        risk_score=alert['risk_score'],
                        risk_level=alert['risk_level'],
                        detection_tier=alert['detection_tier'],
                        message=alert['message'],
                        red_flags=alert['red_flags'],
                        recommended_action=alert['recommended_action']
                    )
                    db.add(db_alert)
                    db.commit()
            except Exception as e:
                logger.error(f"[{call_id}] Failed to save alert to DB: {e}")
    
    except Exception as e:
        logger.error(
            f"[{call_id}] Error handling media event: {e}",
            exc_info=True
        )


async def _finalize_call(call_id: str, detection_service):
    """
    Finalize call after disconnection.
    
    Args:
        call_id: Call identifier
        detection_service: Detection service instance
    """
    try:
        logger.info(f"[{call_id}] Finalizing call")
        
        # Finalize detection (flush remaining audio)
        final_alert = await detection_service.finalize_call(call_id)
        
        # Update call record in database
        with get_db_context() as db:
            call = db.query(Call).filter(Call.call_id == call_id).first()
            
            if call:
                # Get session data
                session = await get_call_session(call_id)
                
                call.end_time = datetime.utcnow()
                
                if call.start_time:
                    duration = (call.end_time - call.start_time).total_seconds()
                    call.duration_seconds = int(duration)
                
                if session:
                    call.final_risk_score = session.get('max_risk_score', 0)
                    
                    if call.final_risk_score >= 85:
                        call.final_risk_level = "high"
                        call.is_scam = True
                    elif call.final_risk_score >= 50:
                        call.final_risk_level = "medium"
                    else:
                        call.final_risk_level = "low"
                
                call.status = "completed"
                
                db.commit()
        
        # Clean up Redis session
        await delete_call_session(call_id)
        
        logger.info(f"[{call_id}] Call finalized successfully")
    
    except Exception as e:
        logger.error(
            f"[{call_id}] Error finalizing call: {e}",
            exc_info=True
        )


@router.websocket("/demo-call")
async def demo_call_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for browser-based demo calls.
    Receives audio directly from user's microphone for testing.
    """
    call_id = None
    try:
        await websocket.accept()
        call_id = f"demo_{uuid.uuid4().hex[:12]}"
        
        logger.info(f"[{call_id}] ✅ Demo call WebSocket accepted")
        
        # Import here to avoid circular imports
        import io
        import tempfile
        from pydub import AudioSegment
        
        logger.info(f"[{call_id}] 📦 Imports successful")
        
        # Initialize session
        await set_call_session(call_id, {
            "call_id": call_id,
            "status": "active",
            "phone_number": "DEMO",
            "caller_id": "Demo User",
            "start_time": datetime.utcnow().isoformat(),
            "message_count": 0,
            "transcripts": [],
            "alerts": [],
            "max_risk_score": 0
        }, expire_seconds=3600)
        
        logger.info(f"[{call_id}] 💾 Session initialized")
        
        # Create call record
        with get_db_context() as db:
            db_call = Call(
                call_id=call_id,
                phone_number="DEMO",
                caller_id="Demo User",
                status="active"
            )
            db.add(db_call)
            db.commit()
        
        await websocket.send_json({
            "event": "connected",
            "call_id": call_id,
            "message": "Demo call connected. Start speaking!"
        })
        
        # Get services
        from backend.services.whisper_service import get_whisper_service
        from backend.agents.orchestrator import Orchestrator
        
        whisper_service = get_whisper_service()
        orchestrator = Orchestrator()
        
        full_transcript = ""
        
        # Wait for complete audio from browser (with timeout)
        try:
            logger.info(f"[{call_id}] ⏳ Waiting for audio data...")
            
            # Use asyncio.wait_for with a generous timeout
            import asyncio
            audio_data = await asyncio.wait_for(
                websocket.receive_bytes(),
                timeout=300.0  # 5 minutes timeout
            )
            
            logger.info(f"[{call_id}] 📥 Received {len(audio_data)} bytes of complete audio")
            
            # Skip if too small
            if len(audio_data) < 1000:
                logger.warning(f"[{call_id}] Audio too small, skipping")
                await websocket.send_json({
                    "event": "error",
                    "message": "Recording too short - please speak longer"
                })
            else:
                # Convert WebM to PCM for Whisper
                try:
                    logger.info(f"[{call_id}] 🔄 Converting audio...")
                    
                    # Save to temp file and convert with pydub
                    with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_webm:
                        temp_webm.write(audio_data)
                        temp_webm_path = temp_webm.name
                    
                    logger.info(f"[{call_id}] 📁 Saved to temp file: {temp_webm_path}")
                    
                    # Convert to WAV
                    audio = AudioSegment.from_file(temp_webm_path, format="webm")
                    
                    logger.info(f"[{call_id}] ✅ Loaded audio: {len(audio)}ms, {audio.frame_rate}Hz")
                    
                    # Convert to 16kHz mono for Whisper
                    audio = audio.set_frame_rate(16000).set_channels(1)
                    
                    # Convert to numpy array using sample-width-aware scaling
                    import numpy as np
                    sample_array = np.array(audio.get_array_of_samples()).astype(np.float32)
                    scale = float(1 << (8 * audio.sample_width - 1)) if audio.sample_width > 0 else 32768.0
                    audio_array = np.clip(sample_array / scale, -1.0, 1.0)
                    
                    logger.info(
                        f"[{call_id}] ✅ Converted audio: samples={audio_array.shape[0]}, "
                        f"sample_width={audio.sample_width}, frame_rate={audio.frame_rate}"
                    )
                    
                    # Clean up temp file
                    import os
                    os.unlink(temp_webm_path)
                    
                    # Transcribe with Whisper
                    logger.info(f"[{call_id}] 🎤 Transcribing...")
                    # Pass 1: auto-language with VAD
                    result = await whisper_service.transcribe(audio=audio_array, language=None)

                    transcript_text = result.get('text', '').strip()

                    # Pass 2: disable VAD for short/noisy clips
                    if not transcript_text:
                        retry_result = await whisper_service.transcribe(
                            audio=audio_array,
                            language=None,
                            beam_size=1,
                            use_vad=False
                        )
                        if retry_result.get('text', '').strip():
                            result = retry_result
                            transcript_text = retry_result.get('text', '').strip()

                    # Pass 3: boosted gain fallback
                    if not transcript_text:
                        boosted_audio = np.clip(audio_array * 2.5, -1.0, 1.0)
                        boosted_result = await whisper_service.transcribe(
                            audio=boosted_audio,
                            language=None,
                            beam_size=1,
                            use_vad=False
                        )
                        if boosted_result.get('text', '').strip():
                            result = boosted_result
                            transcript_text = boosted_result.get('text', '').strip()
                    
                    logger.info(f"[{call_id}] 📝 Whisper result: {result}")
                    
                    if result.get('error'):
                        logger.warning(f"[{call_id}] ⚠️ Transcription error: {result['error']}")
                        await websocket.send_json({
                            "event": "error",
                            "message": f"Transcription failed: {result['error']}"
                        })
                    else:
                        if not transcript_text:
                            logger.debug(f"[{call_id}] ℹ️ Empty transcript")
                            await websocket.send_json({
                                "event": "error",
                                "message": "No speech detected - please speak clearly and closer to microphone"
                            })
                        else:
                            logger.info(f"[{call_id}] ✅ Transcribed: '{transcript_text}'")
                            full_transcript = transcript_text
                            
                            # Send transcript to frontend
                            await websocket.send_json({
                                "event": "transcript",
                                "text": transcript_text,
                                "timestamp": datetime.utcnow().isoformat()
                            })
                            logger.info(f"[{call_id}] 📤 Sent transcript to frontend")
                            
                            # Run Tier1 detection first (always show score)
                            logger.info(f"[{call_id}] 🔍 Running Tier1 detection on: '{full_transcript}'")
                            tier1_result = await orchestrator.tier1.detect(full_transcript)
                            logger.info(f"[{call_id}] 📊 Tier1 Results - Score: {tier1_result['score']}, Keyword: {tier1_result['keyword_score']}, Pattern: {tier1_result['pattern_score']}")
                            
                            # Send detection score to frontend
                            await websocket.send_json({
                                "event": "detection",
                                "risk_score": tier1_result['score'],
                                "keyword_score": tier1_result['keyword_score'],
                                "pattern_score": tier1_result['pattern_score'],
                                "matched_keywords": tier1_result.get('matched_keywords', []),
                                "matched_pattern": tier1_result.get('matched_pattern')
                            })
                            logger.info(f"[{call_id}] 📤 Sent detection score to frontend")
                            
                            # Update session with max risk score
                            session = await get_call_session(call_id)
                            if session:
                                session['max_risk_score'] = tier1_result['score']
                                await set_call_session(call_id, session)
                                logger.info(f"[{call_id}] Updated max_risk_score: {tier1_result['score']}")
                            
                            # Run full orchestrator detection (for alert generation)
                            logger.info(f"[{call_id}] 🎯 Running full fraud detection...")
                            detection_result = await orchestrator.detect(
                                transcript=full_transcript,
                                call_id=call_id,
                                context={
                                    "duration": len(audio) / 1000,  # duration in seconds
                                    "caller_id": "Demo User",
                                    "phone_number": "DEMO"
                                }
                            )
                            
                            logger.info(f"[{call_id}] 🎯 Detection result: {'ALERT' if detection_result else 'NO ALERT'}")
                            
                            # For DEMO mode: create alert if score > 50 (easier testing)
                            if not detection_result and tier1_result['score'] > 50:
                                logger.info(f"[{call_id}] Creating demo alert (score={tier1_result['score']})")
                                detection_result = {
                                    "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
                                    "call_id": call_id,
                                    "risk_score": tier1_result['score'],
                                    "risk_level": "medium" if tier1_result['score'] < 85 else "high",
                                    "detection_tier": "tier1",
                                    "message": f"⚠️ DEMO ALERT: Potential fraud detected (Score: {tier1_result['score']}/100)",
                                    "red_flags": tier1_result.get('matched_keywords', []),
                                    "recommended_action": "This is a demo call. In production, scores > 50 trigger further analysis.",
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                            
                            # If alert generated, send it
                            if detection_result:
                                logger.warning(f"[{call_id}] 🚨 FRAUD DETECTED! Risk: {detection_result['risk_score']}/100, Level: {detection_result['risk_level']}")
                                
                                await websocket.send_json({
                                    "event": "alert",
                                    **detection_result
                                })
                                logger.info(f"[{call_id}] 📤 Alert sent to frontend")
                                
                                # Save to database
                                try:
                                    with get_db_context() as db:
                                        db_alert = Alert(
                                            alert_id=detection_result['alert_id'],
                                            call_id=call_id,
                                            risk_score=detection_result['risk_score'],
                                            risk_level=detection_result['risk_level'],
                                            detection_tier=detection_result['detection_tier'],
                                            message=detection_result['message'],
                                            red_flags=detection_result['red_flags'],
                                            recommended_action=detection_result['recommended_action']
                                        )
                                        db.add(db_alert)
                                        db.commit()
                                        logger.info(f"[{call_id}] Alert saved to database")
                                except Exception as e:
                                    logger.error(f"[{call_id}] Failed to save alert: {e}")
                            else:
                                # No alert - send info message
                                logger.info(f"[{call_id}] ℹ️ No alert generated (score too low: {tier1_result['score']}/100)")
                                await websocket.send_json({
                                    "event": "info",
                                    "message": f"No fraud detected. Risk score: {tier1_result['score']}/100. Try using more fraud keywords!"
                                })
                
                except Exception as e:
                    logger.error(f"[{call_id}] Audio processing error: {e}", exc_info=True)
                    await websocket.send_json({
                        "event": "error",
                        "message": f"Failed to process audio: {str(e)[:100]}"
                    })
        
        except asyncio.TimeoutError:
            logger.warning(f"[{call_id}] Timeout waiting for audio data")
            await websocket.send_json({
                "event": "error",
                "message": "Timeout waiting for audio. Please try again."
            })
        
        except WebSocketDisconnect:
            logger.info(f"[{call_id}] Demo call disconnected")
    
    except Exception as e:
        error_msg = f"Backend error: {str(e)}"
        logger.error(f"[{call_id or 'unknown'}] ❌ Demo call fatal error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "event": "error",
                "message": error_msg
            })
        except:
            pass  # WebSocket might already be closed
    
    finally:
        # Update call record with final risk scores
        if call_id:
            try:
                with get_db_context() as db:
                    call = db.query(Call).filter(Call.call_id == call_id).first()
                    if call:
                        # Get session data
                        session = await get_call_session(call_id)
                        
                        call.end_time = datetime.utcnow()
                        
                        if call.start_time:
                            duration = (call.end_time - call.start_time).total_seconds()
                            call.duration_seconds = int(duration)
                        
                        if session:
                            call.final_risk_score = session.get('max_risk_score', 0)
                            
                            if call.final_risk_score >= 85:
                                call.final_risk_level = "high"
                                call.is_scam = True
                            elif call.final_risk_score >= 50:
                                call.final_risk_level = "medium"
                            else:
                                call.final_risk_level = "low"
                        
                        call.status = "completed"
                        
                        db.commit()
                        logger.info(f"[{call_id}] Updated call record - Risk: {call.final_risk_score}, Is Scam: {call.is_scam}")
            except Exception as e:
                logger.error(f"[{call_id}] Failed to update call: {e}")
            
            # Cleanup session
            try:
                await delete_call_session(call_id)
            except Exception as e:
                logger.error(f"[{call_id}] Failed to cleanup session: {e}")
            
            logger.info(f"[{call_id}] Demo call ended")

