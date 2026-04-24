"""Detection service coordinator."""
import sys
from pathlib import Path
import asyncio
import logging
from typing import Optional, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.audio_service import AudioService, AudioBuffer
from backend.services.whisper_service import get_whisper_service
from backend.agents.orchestrator import Orchestrator
from backend.utils.redis_client import (
    get_call_session, 
    update_call_session, 
    publish_alert
)

logger = logging.getLogger(__name__)


class DetectionService:
    """
    Coordinates the complete detection pipeline:
    1. Audio processing
    2. Speech-to-text (Whisper)
    3. Fraud detection (Tier1/Tier2)
    4. Alert generation
    """

    def __init__(self):
        """Initialize detection service."""
        self.audio_service = AudioService()
        self.whisper_service = get_whisper_service()
        self.orchestrator = Orchestrator()
        
        # Call-specific buffers (will be managed per call)
        self.call_buffers: Dict[str, AudioBuffer] = {}

    def get_or_create_buffer(self, call_id: str) -> AudioBuffer:
        """Get or create audio buffer for a call."""
        if call_id not in self.call_buffers:
            self.call_buffers[call_id] = AudioBuffer(duration_seconds=2.0)
        
        return self.call_buffers[call_id]

    def cleanup_buffer(self, call_id: str):
        """Clean up buffer for a call."""
        if call_id in self.call_buffers:
            del self.call_buffers[call_id]

    async def process_audio_chunk(
        self,
        call_id: str,
        mulaw_bytes: bytes,
        timestamp: str
    ) -> Optional[Dict]:
        """
        Process a single audio chunk from Twilio.
        
        This is called for every 20ms audio chunk.
        Returns alert only when speech is transcribed and analyzed.
        
        Args:
            call_id: Call identifier
            mulaw_bytes: Raw μ-law audio bytes from Twilio
            timestamp: Chunk timestamp
            
        Returns:
            Alert dict if triggered, None otherwise
        """
        try:
            # Process audio chunk
            processed_audio = self.audio_service.process_chunk(
                mulaw_bytes,
                original_sample_rate=8000  # Twilio sends at 8kHz
            )
            
            if len(processed_audio) == 0:
                logger.debug(f"[{call_id}] Empty audio chunk")
                return None
            
            # Add to buffer
            buffer = self.get_or_create_buffer(call_id)
            buffered_audio = buffer.add(processed_audio)
            
            # If buffer is full, transcribe and detect
            if buffered_audio is not None:
                logger.debug(
                    f"[{call_id}] Audio buffer full "
                    f"({len(buffered_audio)} samples), "
                    "transcribing..."
                )
                
                return await self._analyze_buffer(
                    call_id=call_id,
                    audio=buffered_audio,
                    timestamp=timestamp
                )
            
            return None
        
        except Exception as e:
            logger.error(
                f"[{call_id}] Error processing audio chunk: {e}",
                exc_info=True
            )
            return None

    async def _analyze_buffer(
        self,
        call_id: str,
        audio,
        timestamp: str
    ) -> Optional[Dict]:
        """
        Analyze buffered audio segment.
        
        Steps:
        1. Transcribe with Whisper
        2. Run fraud detection
        3. Generate alert if needed
        4. Publish alert to frontend
        
        Args:
            call_id: Call ID
            audio: Audio samples to transcribe
            timestamp: Audio timestamp
            
        Returns:
            Alert dict if created, None otherwise
        """
        # Transcribe audio
        logger.debug(f"[{call_id}] Transcribing {len(audio)} samples")
        
        whisper_result = await self.whisper_service.transcribe(
            audio=audio,
            language="en"
        )
        
        if whisper_result.get('error'):
            logger.warning(
                f"[{call_id}] Transcription error: "
                f"{whisper_result['error']}"
            )
            return None
        
        transcript = whisper_result.get('text', '').strip()
        confidence = whisper_result.get('confidence', 0)
        
        if not transcript:
            logger.debug(f"[{call_id}] No speech detected")
            return None
        
        logger.info(
            f"[{call_id}] Transcribed: '{transcript[:100]}...' "
            f"(confidence: {confidence:.2f})"
        )
        
        # Get call context
        session = await get_call_session(call_id)
        context = {
            'duration': session.get('duration', 0) if session else 0,
            'message_count': session.get('message_count', 0) if session else 1,
            'caller_id': session.get('caller_id', 'Unknown') if session else 'Unknown',
            'timestamp': timestamp,
            'transcription_confidence': confidence
        }
        
        # Run fraud detection
        logger.debug(f"[{call_id}] Running fraud detection on transcript")
        alert = await self.orchestrator.detect(
            transcript=transcript,
            call_id=call_id,
            context=context
        )
        
        # Update session with new transcript
        if session:
            if 'transcripts' not in session:
                session['transcripts'] = []
            
            session['transcripts'].append({
                'text': transcript,
                'timestamp': timestamp,
                'confidence': confidence
            })
            
            session['message_count'] = len(session['transcripts'])
            
            # Update high water mark for risk
            if alert:
                current_risk = session.get('max_risk_score', 0)
                session['max_risk_score'] = max(
                    current_risk,
                    alert.get('risk_score', 0)
                )
            
            await update_call_session(call_id, session)
        
        # Publish alert to frontend
        if alert:
            logger.warning(
                f"[{call_id}] ALERT TRIGGERED: "
                f"{alert.get('message')} "
                f"(risk: {alert.get('risk_score')}/100)"
            )
            
            await publish_alert(alert)
        
        return alert

    async def finalize_call(self, call_id: str) -> Optional[Dict]:
        """
        Finalize call and flush any remaining audio.
        
        Called when call ends.
        
        Args:
            call_id: Call ID
            
        Returns:
            Final alert if any unprocessed audio triggers one
        """
        try:
            buffer = self.get_or_create_buffer(call_id)
            
            # Flush remaining data if any
            if buffer.has_data():
                logger.debug(
                    f"[{call_id}] Flushing remaining audio "
                    f"at call end"
                )
                
                remaining_audio = buffer.flush()
                
                if len(remaining_audio) > 0:
                    alert = await self._analyze_buffer(
                        call_id=call_id,
                        audio=remaining_audio,
                        timestamp=None
                    )
                    return alert
            
            # Clean up
            self.cleanup_buffer(call_id)
            
            logger.info(f"[{call_id}] Call finalized")
            return None
        
        except Exception as e:
            logger.error(
                f"[{call_id}] Error finalizing call: {e}",
                exc_info=True
            )
            self.cleanup_buffer(call_id)
            return None


# Singleton instance
_detection_service: Optional[DetectionService] = None


def get_detection_service() -> DetectionService:
    """Get or create detection service singleton."""
    global _detection_service
    
    if _detection_service is None:
        _detection_service = DetectionService()
        logger.info("Detection service initialized")
    
    return _detection_service
