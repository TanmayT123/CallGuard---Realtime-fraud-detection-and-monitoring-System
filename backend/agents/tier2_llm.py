"""Tier 2 LLM-based fraud detection using Ollama."""
import sys
from pathlib import Path
import json
import logging
import asyncio
from typing import Optional, Dict, List
import httpx
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import settings

logger = logging.getLogger(__name__)


class Tier2LLM:
    """
    Tier 2 deep fraud detection using LLM (Ollama).
    
    For medium-confidence detections (50-85), uses LLM for contextual analysis.
    Speed: 1-3 seconds (depends on Ollama availability)
    """

    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        timeout: float = 2.0
    ):
        """
        Initialize Tier2 LLM detector.
        
        Args:
            base_url: Ollama server URL
            model: LLM model to use
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_model
        self.timeout = timeout
        self.available = False
        
        # Check if Ollama is available
        asyncio.create_task(self._check_availability())

    async def _check_availability(self):
        """Check if Ollama server is available."""
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                self.available = response.status_code == 200
                if self.available:
                    logger.info(f"Ollama server available at {self.base_url}")
                else:
                    logger.warning("Ollama server not responding")
        except Exception as e:
            logger.warning(f"Ollama server not available: {e}")
            self.available = False

    def _build_prompt(
        self, 
        transcript: str, 
        context: Dict
    ) -> str:
        """
        Build detailed prompt for LLM analysis.
        
        Args:
            transcript: Call transcript text
            context: Call context (duration, history, etc.)
            
        Returns:
            Formatted prompt string
        """
        prompt = f"""You are an expert fraud detection AI analyzing phone calls for scams.

CALL TRANSCRIPT:
{transcript}

CALL CONTEXT:
- Duration: {context.get('duration', 'Unknown')} seconds
- Previous messages: {context.get('message_count', 0)} messages
- Caller ID: {context.get('caller_id', 'Unknown/Blocked')}
- Call time: {context.get('timestamp', 'Unknown')}

ANALYZE THIS CALL FOR FRAUD. Consider:
1. Urgency tactics (threats, time pressure)
2. Authority impersonation (government, banks, tech companies)
3. Information requests (credentials, financial data)
4. Payment demands (gift cards, wire transfers, cryptocurrency)
5. Emotional manipulation (fear, greed, confusion)
6. Legitimate red flags (no caller verification, demand for payment, etc.)

Respond ONLY in valid JSON format with NO additional text:
{{
    "is_scam": true/false,
    "risk_score": 0-100,
    "scam_type": "type_name or null",
    "confidence": 0-100,
    "red_flags": ["flag1", "flag2", "flag3"],
    "reasoning": "brief explanation of why/why not a scam",
    "recommended_action": "what user should do"
}}

Rules:
- risk_score: 0-100, higher = more likely scam
- confidence: certainty of assessment 0-100
- red_flags: list of detected suspicious elements
- be concise but thorough
"""
        return prompt

    async def analyze(
        self,
        transcript: str,
        context: Dict,
        timeout: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Analyze transcript using LLM.
        
        Args:
            transcript: Call transcript text
            context: Call context information
            timeout: Override default timeout
            
        Returns:
            Analysis result dict, or None if failed/timeout
        """
        # Check availability
        if not self.available:
            logger.warning("Ollama not available, skipping Tier2")
            return None
        
        timeout = timeout or self.timeout
        
        try:
            prompt = self._build_prompt(transcript, context)
            
            logger.debug(f"Sending request to Ollama ({self.model})")
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "temperature": 0.0,  # Deterministic
                    }
                )
            
            if response.status_code != 200:
                logger.error(f"Ollama API error: {response.status_code}")
                return None
            
            result = response.json()
            response_text = result.get('response', '')
            
            # Parse JSON response
            analysis = self._parse_response(response_text)
            
            if analysis:
                # Ensure all required fields
                analysis.setdefault('is_scam', False)
                analysis.setdefault('risk_score', 0)
                analysis.setdefault('confidence', 50)
                analysis.setdefault('red_flags', [])
                analysis.setdefault('reasoning', '')
                analysis.setdefault('recommended_action', '')
                analysis['tier'] = 'tier2'
                
                logger.info(
                    f"Tier2 analysis complete: "
                    f"is_scam={analysis['is_scam']}, "
                    f"risk_score={analysis['risk_score']}"
                )
                
                return analysis
            else:
                logger.warning("Failed to parse LLM response")
                return None
        
        except asyncio.TimeoutError:
            logger.warning(f"Tier2 analysis timed out after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"Tier2 analysis failed: {e}", exc_info=True)
            return None

    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """
        Parse JSON response from LLM.
        
        Args:
            response_text: Raw response text from LLM
            
        Returns:
            Parsed JSON dict, or None if parsing failed
        """
        try:
            # Try to find JSON in response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end <= json_start:
                logger.warning("No JSON found in LLM response")
                return None
            
            json_str = response_text[json_start:json_end]
            parsed = json.loads(json_str)
            
            # Validate required fields
            if 'risk_score' in parsed and isinstance(parsed['risk_score'], (int, float)):
                return parsed
            else:
                logger.warning("Invalid response format")
                return None
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text[:200]}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing response: {e}")
            return None


class LocalLLMFallback:
    """
    Fallback rules-based detector when Ollama is not available.
    Uses simple heuristics for Tier2 decisions.
    """

    @staticmethod
    def analyze(transcript: str, tier1_result: Dict) -> Dict:
        """
        Fallback analysis using rules.
        
        Args:
            transcript: Call transcript
            tier1_result: Tier1 detection result
            
        Returns:
            Fallback analysis result
        """
        # Use Tier1 score as base
        tier1_score = tier1_result.get('score', 0)
        
        # Enhanced analysis based on content
        factors = []
        adjustment = 0
        
        # Check for multiple urgency indicators
        urgency_words = ['urgent', 'immediately', 'right now', 'hurry']
        urgency_count = sum(1 for w in urgency_words if w in transcript.lower())
        if urgency_count >= 2:
            adjustment += 10
            factors.append("Multiple urgency tactics detected")
        
        # Check for authority claims
        authorities = ['irs', 'fbi', 'social security', 'government']
        if any(a in transcript.lower() for a in authorities):
            adjustment += 10
            factors.append("Authority impersonation suspected")
        
        # Check for payment pressure
        payments = ['gift card', 'wire transfer', 'cryptocurrency']
        if any(p in transcript.lower() for p in payments):
            adjustment += 15
            factors.append("Suspicious payment request detected")
        
        # Calculate final score
        final_score = min(tier1_score + adjustment, 100)
        
        return {
            "is_scam": final_score > 60,
            "risk_score": final_score,
            "confidence": 60,
            "red_flags": factors,
            "reasoning": f"Fallback analysis: Tier1 score {tier1_score} + adjustments",
            "recommended_action": "Be cautious with this call",
            "tier": "tier2_fallback"
        }
