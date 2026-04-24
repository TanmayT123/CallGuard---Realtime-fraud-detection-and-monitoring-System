"""Whisper speech-to-text service."""
import numpy as np
import logging
from typing import Optional
from pathlib import Path
from backend.config import settings

logger = logging.getLogger(__name__)


class WhisperService:
    """
    Wrapper around faster-whisper for speech-to-text.
    
    Converts audio to text with confidence scores.
    Runs locally using OpenAI's Whisper model.
    """

    def __init__(self, model_size: str = "base"):
        """
        Initialize Whisper service.
        
        Model sizes:
        - tiny: ~75MB, very fast, ~70% accuracy
        - base: ~150MB, fast, ~80% accuracy ✅ RECOMMENDED
        - small: ~500MB, medium, ~85% accuracy
        - medium: ~1.5GB, slow, ~90% accuracy
        
        Args:
            model_size: Size of Whisper model to use
        """
        self.model_size = model_size
        self.model = None
        self.device = "cpu"  # "cuda" if GPU available
        
        # Initialize on first use (lazy loading)
        self._initialized = False

    def _initialize_model(self):
        """Initialize the Whisper model (lazy loading)."""
        if self._initialized:
            return
        
        try:
            from faster_whisper import WhisperModel
            
            logger.info(f"Loading Whisper {self.model_size} model...")
            
            # Determine device
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.device = device
            
            self.model = WhisperModel(
                self.model_size,
                device=device,
                compute_type="int8",  # Quantized for speed
                local_files_only=False  # Download if needed
            )
            
            self._initialized = True
            logger.info(f"Whisper model loaded on {device}")
        
        except ImportError:
            logger.error("faster-whisper not installed. Install with: pip install faster-whisper")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Whisper model: {e}")
            raise

    async def transcribe(
        self,
        audio: np.ndarray,
        language: Optional[str] = "en",
        beam_size: int = 5,
        use_vad: bool = True
    ) -> dict:
        """
        Transcribe audio to text.
        
        Args:
            audio: Audio samples (float32, normalized)
            language: Language code (e.g., 'en', 'es') or None for auto-detect
            beam_size: Beam search width (higher = more accurate but slower)
            use_vad: Enable built-in VAD filtering
            
        Returns:
            Dictionary with:
                - text: Transcribed text
                - confidence: Average confidence score (0-1)
                - language: Detected language
                - segments: List of segments with timing
        """
        if not self._initialized:
            self._initialize_model()
        
        if self.model is None:
            logger.error("Whisper model not initialized")
            return {
                "text": "",
                "confidence": 0.0,
                "language": language,
                "segments": [],
                "error": "Model not initialized"
            }
        
        if len(audio) == 0:
            logger.warning("Empty audio for transcription")
            return {
                "text": "",
                "confidence": 0.0,
                "language": language,
                "segments": [],
                "error": "Empty audio"
            }
        
        try:
            # Transcribe audio
            segments, info = self.model.transcribe(
                audio,
                language=language,
                beam_size=beam_size,
                vad_filter=use_vad,
                temperature=0.0   # Deterministic output
            )
            
            # Extract segments and combine text
            segments_list = []
            texts = []
            confidences = []
            
            for segment in segments:
                segments_list.append({
                    "text": segment.text,
                    "start": segment.start,
                    "end": segment.end,
                    "confidence": segment.avg_logprob,
                    "no_speech_prob": segment.no_speech_prob
                })
                texts.append(segment.text)
                confidences.append(segment.avg_logprob)
            
            # Combine text
            combined_text = " ".join(texts).strip()
            
            # Calculate average confidence
            avg_confidence = (
                float(np.mean(confidences)) 
                if confidences 
                else 0.0
            )
            
            # Convert confidence from logprob to probability
            # Clamp negative log probs to 0-1 range
            avg_confidence = min(max(avg_confidence, 0), 1)
            
            return {
                "text": combined_text,
                "confidence": avg_confidence,
                "language": info.language,
                "segments": segments_list,
                "duration": info.duration,
                "error": None
            }
        
        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            return {
                "text": "",
                "confidence": 0.0,
                "language": language,
                "segments": [],
                "error": str(e)
            }

    def is_initialized(self) -> bool:
        """Check if model is initialized."""
        return self._initialized

    def unload_model(self):
        """Unload model from memory."""
        if self.model is not None:
            del self.model
            self.model = None
            self._initialized = False
            logger.info("Whisper model unloaded")


# Singleton instance
_whisper_service: Optional[WhisperService] = None


def get_whisper_service(model_size: str = "base") -> WhisperService:
    """
    Get Whisper service singleton.
    
    Args:
        model_size: Size of model to use
        
    Returns:
        WhisperService instance
    """
    global _whisper_service
    
    if _whisper_service is None:
        _whisper_service = WhisperService(model_size=model_size)
    
    return _whisper_service
