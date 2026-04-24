"""REST API routes for the fraud detection system."""
import sys
from pathlib import Path
import logging
import uuid
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query, HTTPException, Request, UploadFile, File
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.models import get_db
from backend.models.database import Call, Alert, Transcript, DetectionLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


def _to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """Return ISO timestamp with explicit UTC timezone suffix (Z)."""
    if not dt:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.isoformat().replace("+00:00", "Z")


@router.get("/test-simple")
async def test_simple():
    """Simple test endpoint."""
    print("DEBUG: Test endpoint called!")
    return {"message": "Test endpoint working", "timestamp": _to_utc_iso(datetime.utcnow())}


@router.get("/calls")
async def get_calls(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get list of calls.
    
    Query Parameters:
        - limit: Number of results (max 100)
        - offset: Pagination offset
        - status: Filter by status (active, completed, failed)
    
    Returns:
        List of calls with metadata
    """
    query = db.query(Call)
    
    if status:
        query = query.filter(Call.status == status)
    
    total = query.count()
    calls = query.order_by(Call.start_time.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "calls": [
            {
                "call_id": call.call_id,
                "phone_number": call.phone_number,
                "caller_id": call.caller_id,
                "start_time": _to_utc_iso(call.start_time),
                "end_time": _to_utc_iso(call.end_time),
                "duration_seconds": call.duration_seconds,
                "status": call.status,
                "risk_score": call.final_risk_score,
                "risk_level": call.final_risk_level,
                "is_scam": call.is_scam
            }
            for call in calls
        ]
    }


@router.get("/calls/{call_id}")
async def get_call_detail(
    call_id: str,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific call.
    
    Returns:
        Call details including transcripts and alerts
    """
    call = db.query(Call).filter(Call.call_id == call_id).first()
    
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    
    # Get transcripts
    transcripts = db.query(Transcript).filter(
        Transcript.call_id == call_id
    ).order_by(Transcript.timestamp).all()
    
    # Get alerts
    alerts = db.query(Alert).filter(
        Alert.call_id == call_id
    ).order_by(Alert.timestamp).all()
    
    return {
        "call_id": call.call_id,
        "phone_number": call.phone_number,
        "caller_id": call.caller_id,
        "start_time": _to_utc_iso(call.start_time),
        "end_time": _to_utc_iso(call.end_time),
        "duration_seconds": call.duration_seconds,
        "status": call.status,
        "risk_score": call.final_risk_score,
        "risk_level": call.final_risk_level,
        "is_scam": call.is_scam,
        "transcripts": [
            {
                "text": t.text,
                "timestamp": _to_utc_iso(t.timestamp),
                "confidence": t.confidence,
                "language": t.language
            }
            for t in transcripts
        ],
        "alerts": [
            {
                "alert_id": a.alert_id,
                "risk_score": a.risk_score,
                "risk_level": a.risk_level,
                "detection_tier": a.detection_tier,
                "message": a.message,
                "red_flags": a.red_flags,
                "timestamp": _to_utc_iso(a.timestamp)
            }
            for a in alerts
        ]
    }


@router.get("/alerts")
async def get_alerts(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    risk_level: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """
    Get list of fraud alerts.
    
    Query Parameters:
        - limit: Number of results (max 100)
        - offset: Pagination offset
        - risk_level: Filter by risk level (low, medium, high)
        - days: Look back this many days (default: 30)
    
    Returns:
        List of alerts
    """
    import json
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    query = db.query(Alert).filter(Alert.timestamp >= cutoff_date)
    
    if risk_level:
        query = query.filter(Alert.risk_level == risk_level)
    
    total = query.count()
    alerts = query.order_by(Alert.timestamp.desc()).offset(offset).limit(limit).all()
    
    def safe_json_loads(value):
        """Safely parse JSON, return empty list/dict if it fails."""
        if not value:
            return []
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "alerts": [
            {
                "alert_id": a.alert_id,
                "call_id": a.call_id,
                "risk_score": a.risk_score,
                "risk_level": a.risk_level,
                "detection_tier": a.detection_tier,
                "message": a.message,
                "red_flags": safe_json_loads(a.red_flags),
                "timestamp": _to_utc_iso(a.timestamp),
                "details": safe_json_loads(a.alert_metadata)
            }
            for a in alerts
        ]
    }


@router.get("/transcripts/{call_id}")
async def get_transcripts(
    call_id: str,
    db: Session = Depends(get_db)
):
    """
    Get all transcripts for a call.
    
    Returns:
        List of transcribed text segments
    """
    transcripts = db.query(Transcript).filter(
        Transcript.call_id == call_id
    ).order_by(Transcript.sequence, Transcript.timestamp).all()
    
    if not transcripts:
        raise HTTPException(status_code=404, detail="No transcripts found")
    
    return {
        "call_id": call_id,
        "transcripts": [
            {
                "text": t.text,
                "timestamp": _to_utc_iso(t.timestamp),
                "confidence": t.confidence,
                "language": t.language,
                "sequence": t.sequence
            }
            for t in transcripts
        ]
    }


@router.get("/statistics")
async def get_statistics(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """
    Get fraud detection statistics.
    
    Query Parameters:
        - days: Look back this many days (default: 30)
    
    Returns:
        Statistics about calls and detections
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Total calls
    total_calls = db.query(Call).filter(Call.start_time >= cutoff_date).count()
    
    # Scam calls detected
    scam_calls = db.query(Call).filter(
        Call.start_time >= cutoff_date,
        Call.is_scam == True
    ).count()
    
    # Alerts by risk level
    high_alerts = db.query(Alert).filter(
        Alert.timestamp >= cutoff_date,
        Alert.risk_level == "high"
    ).count()
    
    medium_alerts = db.query(Alert).filter(
        Alert.timestamp >= cutoff_date,
        Alert.risk_level == "medium"
    ).count()
    
    # Average call duration
    calls = db.query(Call).filter(Call.start_time >= cutoff_date).all()
    durations = [c.duration_seconds for c in calls if c.duration_seconds]
    avg_duration = sum(durations) / len(durations) if durations else 0
    
    return {
        "period_days": days,
        "total_calls": total_calls,
        "scam_calls": scam_calls,
        "scam_percentage": (scam_calls / total_calls * 100) if total_calls > 0 else 0,
        "high_risk_alerts": high_alerts,
        "medium_risk_alerts": medium_alerts,
        "average_call_duration": int(avg_duration)
    }


@router.post("/demo/upload-audio")
async def demo_upload_audio(
    audio_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Analyze an uploaded recording for demo purposes.

    This endpoint mirrors demo-call behavior without requiring microphone input:
    1. Accept uploaded audio (webm/mp3/wav/m4a supported by ffmpeg/pydub)
    2. Transcribe using Whisper
    3. Run fraud detection pipeline (Tier1 + orchestrator)
    4. Save call/transcript/alert records to database
    """
    import os
    import tempfile
    import numpy as np
    from pydub import AudioSegment
    from backend.services.whisper_service import get_whisper_service
    from backend.agents.orchestrator import Orchestrator

    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    file_bytes = await audio_file.read()
    if len(file_bytes) < 1000:
        raise HTTPException(status_code=400, detail="Uploaded audio is too short")

    temp_path = None
    try:
        file_suffix = Path(audio_file.filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(suffix=file_suffix, delete=False) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        # Load and normalize audio for Whisper
        audio = AudioSegment.from_file(temp_path)
        duration_seconds = max(1, int(len(audio) / 1000))
        audio = audio.set_frame_rate(16000).set_channels(1)

        # Use sample-width-aware conversion to avoid corrupt data for non-int16 sources
        sample_array = np.array(audio.get_array_of_samples()).astype(np.float32)
        scale = float(1 << (8 * audio.sample_width - 1)) if audio.sample_width > 0 else 32768.0
        audio_array = sample_array / scale
        audio_array = np.clip(audio_array, -1.0, 1.0)

        # Transcribe
        whisper_service = get_whisper_service()
        # Pass 1: auto language with VAD
        result = await whisper_service.transcribe(audio=audio_array, language=None)
        transcript_text = result.get("text", "").strip()

        # Pass 2 fallback: disable VAD and reduce beam for noisy clips
        if not transcript_text:
            retry_result = await whisper_service.transcribe(
                audio=audio_array,
                language=None,
                beam_size=1,
                use_vad=False
            )
            if retry_result.get("text", "").strip():
                result = retry_result
                transcript_text = retry_result.get("text", "").strip()

        # Pass 3 fallback: boost low-volume recordings
        if not transcript_text:
            boosted_audio = np.clip(audio_array * 2.5, -1.0, 1.0)
            boosted_result = await whisper_service.transcribe(
                audio=boosted_audio,
                language=None,
                beam_size=1,
                use_vad=False
            )
            if boosted_result.get("text", "").strip():
                result = boosted_result
                transcript_text = boosted_result.get("text", "").strip()

        if result.get("error") and not transcript_text:
            raise HTTPException(
                status_code=422,
                detail=f"Transcription failed: {result['error']}"
            )

        if not transcript_text:
            raise HTTPException(
                status_code=422,
                detail="No speech detected in uploaded recording. Try a clearer WAV/MP3 clip or louder segment."
            )

        call_id = f"demo_upload_{uuid.uuid4().hex[:12]}"

        # Save call + transcript first
        db_call = Call(
            call_id=call_id,
            phone_number="DEMO_UPLOAD",
            caller_id="Demo Upload",
            status="completed",
            duration_seconds=duration_seconds
        )
        db.add(db_call)

        db_transcript = Transcript(
            call_id=call_id,
            text=transcript_text,
            confidence=result.get("confidence", 0.0),
            language=result.get("language", "en"),
            sequence=1
        )
        db.add(db_transcript)

        # Run detection pipeline
        orchestrator = Orchestrator()
        tier1_result = await orchestrator.tier1.detect(transcript_text)
        detection_result = await orchestrator.detect(
            transcript=transcript_text,
            call_id=call_id,
            context={
                "duration": duration_seconds,
                "caller_id": "Demo Upload",
                "phone_number": "DEMO_UPLOAD"
            }
        )

        # Demo fallback: create alert for score > 50 to simplify showcase
        if not detection_result and tier1_result["score"] > 50:
            detection_result = {
                "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
                "call_id": call_id,
                "risk_score": tier1_result["score"],
                "risk_level": "medium" if tier1_result["score"] < 85 else "high",
                "detection_tier": "tier1",
                "message": f"DEMO ALERT: Potential fraud detected (Score: {tier1_result['score']}/100)",
                "red_flags": tier1_result.get("matched_keywords", []),
                "recommended_action": "Demo upload alert generated from Tier1 score.",
                "details": {
                    "caller_id": "Demo Upload",
                    "phone_number": "DEMO_UPLOAD",
                    "duration": duration_seconds,
                    "is_scam": tier1_result["score"] >= 85
                },
                "timestamp": _to_utc_iso(datetime.utcnow())
            }

        alert_payload = None
        final_risk_score = tier1_result["score"]
        final_risk_level = "low"
        is_scam = False

        if detection_result:
            final_risk_score = detection_result["risk_score"]
            final_risk_level = detection_result["risk_level"]
            is_scam = final_risk_level == "high"

            db_alert = Alert(
                alert_id=detection_result["alert_id"],
                call_id=call_id,
                risk_score=detection_result["risk_score"],
                risk_level=detection_result["risk_level"],
                detection_tier=detection_result["detection_tier"],
                message=detection_result["message"],
                red_flags=detection_result.get("red_flags", []),
                recommended_action=detection_result.get("recommended_action"),
                alert_metadata=detection_result.get("details", {})
            )
            db.add(db_alert)

            alert_payload = {
                "alert_id": detection_result["alert_id"],
                "risk_score": detection_result["risk_score"],
                "risk_level": detection_result["risk_level"],
                "message": detection_result["message"],
                "red_flags": detection_result.get("red_flags", []),
                "detection_tier": detection_result["detection_tier"]
            }
        elif final_risk_score >= 50:
            final_risk_level = "medium"

        db_call.final_risk_score = final_risk_score
        db_call.final_risk_level = final_risk_level
        db_call.is_scam = is_scam

        db.commit()

        return {
            "success": True,
            "call_id": call_id,
            "filename": audio_file.filename,
            "transcript": transcript_text,
            "risk_score": final_risk_score,
            "risk_level": final_risk_level,
            "alert_generated": alert_payload is not None,
            "alert": alert_payload,
            "tier1_details": {
                "keyword_score": tier1_result.get("keyword_score"),
                "pattern_score": tier1_result.get("pattern_score"),
                "vector_score": tier1_result.get("vector_score"),
                "matched_keywords": tier1_result.get("matched_keywords", []),
                "matched_pattern": tier1_result.get("matched_pattern")
            }
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Demo upload analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to analyze uploaded audio: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.get("/detection-logs")
async def get_detection_logs(
    call_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Get detection logs for debugging.
    
    Query Parameters:
        - call_id: Filter by specific call
        - limit: Number of results
        - offset: Pagination offset
    
    Returns:
        List of detection logs
    """
    query = db.query(DetectionLog)
    
    if call_id:
        query = query.filter(DetectionLog.call_id == call_id)
    
    total = query.count()
    logs = query.order_by(DetectionLog.timestamp.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [
            {
                "call_id": log.call_id,
                "transcript": log.transcript[:100] + "..." if len(log.transcript) > 100 else log.transcript,
                "tier1_score": log.tier1_score,
                "tier1_details": log.tier1_details,
                "tier2_triggered": log.tier2_triggered,
                "tier2_score": log.tier2_score,
                "processing_time_ms": log.processing_time_ms,
                "timestamp": _to_utc_iso(log.timestamp)
            }
            for log in logs
        ]
    }


@router.get("/test/detect-text")
async def test_detect_text(
    text: str,
    db: Session = Depends(get_db)
):
    """
    Test fraud detection on raw text (manual testing).
    
    This endpoint allows testing the fraud detection pipeline
    without requiring an actual phone call.
    
    Query Parameters:
        - text: Text to analyze
    
    Returns:
        Detection result with detailed scores
    """
    import asyncio
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from backend.agents.orchestrator import Orchestrator
    
    try:
        orchestrator = Orchestrator()
        
        # Get Tier1 score first for debugging
        tier1_result = await orchestrator.tier1.detect(text)
        
        # Run full detection
        alert = await orchestrator.detect(
            transcript=text,
            call_id=f"test_{datetime.utcnow().timestamp()}",
            context={"duration": 0, "caller_id": "Test"}
        )
        
        # Save alert to database if created
        if alert:
            import json
            # First create a Call record
            test_call = Call(
                call_id=alert.get('call_id'),
                phone_number="TEST",
                caller_id=alert.get('details', {}).get('caller_id', 'Test'),
                status="completed",
                duration_seconds=0,
                final_risk_score=alert.get('risk_score'),
                final_risk_level=alert.get('risk_level'),
                is_scam=alert.get('details', {}).get('is_scam', False)
            )
            db.add(test_call)
            db.flush()  # Flush to ensure call_id is generated
            
            # Then create Alert record
            db_alert = Alert(
                alert_id=alert.get('alert_id'),
                call_id=alert.get('call_id'),
                risk_score=alert.get('risk_score'),
                risk_level=alert.get('risk_level'),
                detection_tier=alert.get('detection_tier'),
                message=alert.get('message'),
                red_flags=json.dumps(alert.get('red_flags', [])),  # Store as JSON
                recommended_action=alert.get('recommended_action'),
                alert_metadata=json.dumps(alert.get('details', {}))  # Store as JSON
            )
            db.add(db_alert)
            db.commit()
            logger.info(f"Call and Alert saved to database: {alert.get('alert_id')}")
        
        return {
            "success": True,
            "tier1_score": tier1_result.get('score'),
            "tier1_details": {
                "keyword_score": tier1_result.get('keyword_score'),
                "pattern_score": tier1_result.get('pattern_score'),
                "vector_score": tier1_result.get('vector_score'),
                "matched_keywords": tier1_result.get('matched_keywords'),
                "matched_pattern": tier1_result.get('matched_pattern')
            },
            "alert": alert,
            "alert_saved": alert is not None,
            "message": "Detection completed"
        }
    
    except Exception as e:
        logger.error(f"Test detection error: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Detection failed"
        }
        return {
            "success": False,
            "error": str(e),
            "message": "Detection failed"
        }
        return {
            "success": False,
            "error": str(e),
            "message": "Detection failed"
        }


@router.get("/scam-patterns")
async def get_scam_patterns(db: Session = Depends(get_db)):
    """
    Get list of known scam patterns.
    
    Returns:
        Scam patterns used for detection
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from backend.agents.tier1_detector import Tier1Detector
    
    detector = Tier1Detector()
    
    patterns = detector.pattern_matcher.patterns
    
    return {
        "count": len(patterns),
        "patterns": [
            {
                "id": p["id"],
                "name": p["name"],
                "description": p["description"],
                "scam_type": p.get("scam_type"),
                "severity": p["score"],
                "keywords": p["keywords"]
            }
            for p in patterns
        ]
    }


@router.post("/twilio/webhook")
async def twilio_webhook(request: Request):
    """
    Twilio webhook handler - initiates real-time audio streaming for fraud detection.
    
    This webhook is called when a call comes in. It returns TwiML that:
    1. Connects the call to WebSocket for real-time audio streaming
    2. Plays a greeting message to the caller
    3. Keeps the call active while audio is analyzed
    """
    import uuid
    
    print("\n" + "="*50)
    print("🚀 INCOMING CALL - Starting Real-time Analysis")
    print("="*50)
    
    try:
        # Parse Twilio form data
        form_data = await request.form()
        call_sid = form_data.get("CallSid", "unknown")
        from_number = form_data.get("From", "Unknown")
        to_number = form_data.get("To", "Unknown")
        
        print(f"📞 CallSid: {call_sid}")
        print(f"📱 From: {from_number} → To: {to_number}")
        
        # Generate unique call ID for tracking
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        print(f"✅ Generated call_id: {call_id}")
        
        # Get WebSocket URL from settings
        from backend.config import settings
        websocket_url = f"{settings.ngrok_url}/ws/call/{call_id}?phone_number={from_number}&caller_id={from_number}"
        
        print(f"🌐 WebSocket URL: {websocket_url}")
        print("🎤 Starting real-time audio stream...")
        print("="*50 + "\n")
        
        # Return TwiML that connects call to WebSocket for audio streaming
        twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Your call is being analyzed for security purposes.</Say>
    <Start>
        <Stream url="{websocket_url}" />
    </Start>
    <Pause length="30"/>
</Response>'''
        
        return PlainTextResponse(
            content=twiml,
            media_type="application/xml"
        )
        
    except Exception as error:
        print(f"❌ WEBHOOK ERROR: {str(error)}")
        import traceback
        traceback.print_exc()
        
        return PlainTextResponse(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Say>Error processing call</Say></Response>',
            media_type="application/xml"
        )


@router.get("/twilio/setup")
async def twilio_setup():
    """
    Instructions for setting up Twilio webhook.
    
    Returns:
        Setup instructions with webhook URL
    """
    return {
        "status": "success",
        "webhook_endpoint": "/api/twilio/webhook",
        "setup_instructions": {
            "step_1": "Get ngrok URL by running: ngrok http 8000",
            "step_2": "Replace 'your-ngrok-url.ngrok.io' in twilio/webhook endpoint with your ngrok URL",
            "step_3": "Go to Twilio Console → Phone Numbers → Your Number",
            "step_4": "Set 'A call comes in' webhook to: https://your-ngrok-url.ngrok.io/api/twilio/webhook",
            "step_5": "Method: POST",
            "step_6": "Save and test by calling your Twilio number"
        },
        "example_webhook_url": "https://abc123.ngrok.io/api/twilio/webhook",
        "websocket_endpoint": "/ws/call/{call_id}"
    }
