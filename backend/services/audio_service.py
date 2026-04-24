"""Audio processing service."""
import sys
from pathlib import Path
import numpy as np
import logging
from typing import Optional, Tuple
import audioop

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import settings

logger = logging.getLogger(__name__)


class AudioBuffer:
    """Manages audio buffering for processing."""

    def __init__(self, duration_seconds: float = 2.0, sample_rate: int = 16000):
        """
        Initialize audio buffer.
        
        Args:
            duration_seconds: Buffer duration in seconds
            sample_rate: Audio sample rate in Hz
        """
        self.duration_seconds = duration_seconds
        self.sample_rate = sample_rate
        self.max_samples = int(duration_seconds * sample_rate)
        self.buffer: list = []
        self.sample_count = 0

    def add(self, audio_data: np.ndarray) -> Optional[np.ndarray]:
        """
        Add audio data to buffer.
        
        Args:
            audio_data: Audio samples as numpy array
            
        Returns:
            Flushed audio data if buffer is full, None otherwise
        """
        self.buffer.append(audio_data)
        self.sample_count += len(audio_data)
        
        if self.sample_count >= self.max_samples:
            return self.flush()
        
        return None

    def flush(self) -> np.ndarray:
        """
        Get all buffered audio and clear buffer.
        
        Returns:
            Combined audio data as numpy array
        """
        if not self.buffer:
            return np.array([], dtype=np.float32)
        
        combined = np.concatenate(self.buffer)
        self.buffer = []
        self.sample_count = 0
        
        return combined.astype(np.float32)

    def has_data(self) -> bool:
        """Check if buffer has data."""
        return len(self.buffer) > 0

    def get_pending_data(self) -> Optional[np.ndarray]:
        """Get current buffer data without flushing (for monitoring)."""
        if not self.buffer:
            return None
        return np.concatenate(self.buffer).astype(np.float32)


class AudioService:
    """Handles audio format conversion, VAD, and buffering."""

    def __init__(self):
        """Initialize audio service."""
        self.sample_rate = settings.audio_sample_rate
        self.chunk_duration_ms = settings.audio_chunk_duration_ms
        
        # Initialize VAD model (Silero VAD)
        try:
            self.vad_model = self._init_vad()
            logger.info("VAD model initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize VAD: {e}. VAD will be disabled.")
            self.vad_model = None

    def _init_vad(self):
        """Initialize Silero VAD model."""
        try:
            import torch
            # Try to load the model
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False
            )
            return model
        except Exception as e:
            logger.warning(f"Silero VAD not available: {e}")
            return None

    def decode_mulaw(self, mulaw_bytes: bytes) -> np.ndarray:
        """
        Convert μ-law encoded audio to PCM 16-bit.
        
        Twilio sends audio as μ-law encoded (8-bit).
        We need to convert to PCM (16-bit) for Whisper.
        
        Args:
            mulaw_bytes: Raw μ-law audio bytes
            
        Returns:
            PCM audio as numpy array (float32, normalized)
        """
        try:
            # audioop.ulaw2lin converts μ-law to PCM (16-bit)
            pcm_bytes = audioop.ulaw2lin(mulaw_bytes, 2)
            
            # Convert bytes to numpy array
            pcm_data = np.frombuffer(pcm_bytes, dtype=np.int16)
            
            # Normalize to float32 (-1.0 to 1.0)
            audio = pcm_data.astype(np.float32) / 32768.0
            
            return audio
        except Exception as e:
            logger.error(f"Failed to decode μ-law audio: {e}")
            return np.array([], dtype=np.float32)

    def resample_if_needed(
        self, 
        audio: np.ndarray, 
        original_rate: int = 8000, 
        target_rate: int = 16000
    ) -> np.ndarray:
        """
        Resample audio if needed.
        
        Twilio sends at 8kHz, Whisper works better at 16kHz.
        
        Args:
            audio: Audio samples
            original_rate: Original sample rate
            target_rate: Target sample rate
            
        Returns:
            Resampled audio
        """
        if original_rate == target_rate:
            return audio
        
        try:
            import scipy.signal
            
            # Calculate resampling factor
            num_samples = int(len(audio) * target_rate / original_rate)
            
            # Resample using scipy
            resampled = scipy.signal.resample(audio, num_samples)
            return resampled.astype(np.float32)
        except Exception as e:
            logger.warning(f"Resampling failed: {e}. Using original audio.")
            return audio

    def detect_voice_activity(self, audio: np.ndarray) -> bool:
        """
        Detect if audio contains speech (Voice Activity Detection).
        
        Args:
            audio: Audio samples (float32)
            
        Returns:
            True if speech detected, False otherwise
        """
        if self.vad_model is None:
            # VAD disabled, always assume speech
            return True
        
        try:
            import torch
            
            # VAD expects audio tensor
            audio_tensor = torch.from_numpy(audio).float()
            
            # Run VAD model
            confidence = self.vad_model(audio_tensor, self.sample_rate).item()
            
            # Speech detected if confidence > 0.5
            return confidence > 0.5
        except Exception as e:
            logger.debug(f"VAD detection failed: {e}. Assuming speech.")
            return True

    def process_chunk(
        self, 
        mulaw_bytes: bytes,
        original_sample_rate: int = 8000
    ) -> np.ndarray:
        """
        Process a single audio chunk from Twilio.
        
        Steps:
        1. Decode μ-law to PCM
        2. Resample to target rate
        3. Apply gain normalization
        
        Args:
            mulaw_bytes: Raw audio bytes from Twilio
            original_sample_rate: Original sample rate (usually 8kHz)
            
        Returns:
            Processed audio as numpy array
        """
        # Decode μ-law
        audio = self.decode_mulaw(mulaw_bytes)
        
        if len(audio) == 0:
            return audio
        
        # Resample if needed
        if original_sample_rate != self.sample_rate:
            audio = self.resample_if_needed(
                audio, 
                original_sample_rate, 
                self.sample_rate
            )
        
        # Normalize gain (prevent clipping)
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / (max_val * 1.2)  # Leave 20% headroom
        
        return audio.astype(np.float32)

    def get_statistics(self, audio: np.ndarray) -> dict:
        """
        Get audio statistics for monitoring.
        
        Args:
            audio: Audio samples
            
        Returns:
            Dictionary with statistics
        """
        if len(audio) == 0:
            return {
                "rms": 0.0,
                "peak": 0.0,
                "duration_seconds": 0.0,
                "is_silent": True
            }
        
        rms = np.sqrt(np.mean(audio ** 2))
        peak = np.max(np.abs(audio))
        duration = len(audio) / self.sample_rate
        
        return {
            "rms": float(rms),
            "peak": float(peak),
            "duration_seconds": float(duration),
            "is_silent": rms < 0.01  # Threshold for silence
        }
