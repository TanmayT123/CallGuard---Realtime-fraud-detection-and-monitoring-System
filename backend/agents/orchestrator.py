"""Orchestrator for fraud detection pipeline coordination."""
import sys
from pathlib import Path
import logging
import time
from typing import Optional, Dict, List
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.agents.tier1_detector import Tier1Detector
from backend.agents.tier2_llm import Tier2LLM, LocalLLMFallback
from backend.agents.qwen_detector import QwenFraudDetector
from backend.config import settings

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Orchestrates the multi-tier fraud detection pipeline.
    
    Decision flow:
    - Tier1 (Keywords) score > 85: ALERT immediately (high confidence)
    - Tier1 score 50-85: Run Tier2 Qwen ML for accurate analysis
        - If Qwen confidence > 0.7: Use Qwen result
        - If Qwen not confident: Fallback to LLM (Tier3)
    - Tier1 score < 50: Continue monitoring (no alert)
    
    Expected latency:
    - Tier1: <100ms (keyword matching)
    - Tier2 Qwen: 200-500ms (ML inference)
    - Tier3 LLM: 2-5s (Ollama fallback)
    """

    def __init__(self):
        """Initialize orchestrator with detector instances."""
        self.tier1 = Tier1Detector()
        self.tier2_qwen = QwenFraudDetector()  # ML-based detector
        self.tier2_llm = Tier2LLM()
        self.tier2_fallback = LocalLLMFallback()
        
        # Thresholds for decision making
        self.high_threshold = settings.tier1_high_threshold  # 85
        self.medium_threshold = settings.tier1_medium_threshold  # 50

    async def detect(
        self,
        transcript: str,
        call_id: str,
        context: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Run full detection pipeline and return alert if warranted.
        
        Args:
            transcript: Call transcript text
            call_id: Unique call identifier
            context: Call context (duration, caller_id, etc.)
            
        Returns:
            Alert dict if scam detected, None otherwise
        """
        context = context or {}
        start_time = time.time()
        
        try:
            # Always run Tier1 (fast)
            logger.debug(f"[{call_id}] Running Tier1 detection")
            tier1_result = await self.tier1.detect(transcript)
            tier1_score = tier1_result['score']
            
            # Decide next action based on Tier1 score
            alert = None
            
            if tier1_score > self.high_threshold:
                # High confidence - alert immediately
                logger.info(
                    f"[{call_id}] Tier1 high confidence: {tier1_score}/100"
                )
                alert = self._create_alert(
                    call_id=call_id,
                    tier1_result=tier1_result,
                    context=context
                )
            
            elif tier1_score > self.medium_threshold:
                # Medium confidence - get Qwen ML analysis first
                logger.debug(
                    f"[{call_id}] Tier1 medium confidence: {tier1_score}/100, "
                    "running Qwen ML analysis"
                )
                
                # Try Qwen ML first
                qwen_result = await self._run_qwen(
                    transcript=transcript,
                    call_id=call_id,
                    context=context,
                    tier1_result=tier1_result
                )
                
                # Use Qwen result if confident
                if qwen_result and qwen_result.get('confidence', 0) > 0.7:
                    logger.info(
                        f"[{call_id}] Qwen confident: "
                        f"{qwen_result.get('risk_score')}/100 "
                        f"(confidence: {qwen_result.get('confidence')})"
                    )
                    if qwen_result.get('risk_score', 0) > self.medium_threshold:
                        alert = self._create_alert(
                            call_id=call_id,
                            tier2_result=qwen_result,
                            context=context
                        )
                else:
                    # Fallback to LLM if Qwen not confident
                    logger.debug(
                        f"[{call_id}] Qwen not confident, trying LLM fallback"
                    )
                    tier2_result = await self._run_tier2_llm(
                        transcript=transcript,
                        call_id=call_id,
                        context=context,
                        tier1_result=tier1_result
                    )
                    
                    if tier2_result:
                        # Use Tier2 result for decision
                        if tier2_result.get('risk_score', 0) > self.high_threshold:
                            alert = self._create_alert(
                                call_id=call_id,
                                tier2_result=tier2_result,
                                context=context
                            )
                        else:
                            logger.debug(
                                f"[{call_id}] Tier2 confirmed low risk: "
                                f"{tier2_result.get('risk_score')}/100"
                            )
            
            else:
                # Low risk - continue monitoring
                logger.debug(
                    f"[{call_id}] Low risk detected: {tier1_score}/100"
                )
            
            # Log detection result to database
            processing_time_ms = int((time.time() - start_time) * 1000)
            await self._log_detection(
                call_id=call_id,
                transcript=transcript,
                tier1_result=tier1_result,
                alert=alert,
                processing_time_ms=processing_time_ms
            )
            
            return alert
        
        except Exception as e:
            logger.error(
                f"[{call_id}] Detection pipeline error: {e}",
                exc_info=True
            )
            return None

    async def _run_qwen(
        self,
        transcript: str,
        call_id: str,
        context: Dict,
        tier1_result: Dict
    ) -> Optional[Dict]:
        """
        Run Qwen ML analysis.
        
        Args:
            transcript: Call transcript
            call_id: Call ID
            context: Call context
            tier1_result: Tier1 detection result
            
        Returns:
            Qwen result or None if failed
        """
        try:
            logger.debug(f"[{call_id}] Running Qwen ML detection")
            
            # Add tier1 hints to context
            qwen_context = {
                **context,
                'tier1_score': tier1_result.get('score'),
                'tier1_flags': tier1_result.get('flags', [])
            }
            
            qwen_result = await self.tier2_qwen.detect(
                transcript=transcript,
                call_id=call_id,
                context=qwen_context
            )
            
            if qwen_result:
                logger.info(
                    f"[{call_id}] Qwen detected: "
                    f"Risk={qwen_result.get('risk_score')}/100, "
                    f"Type={qwen_result.get('fraud_type', 'unknown')}, "
                    f"Confidence={qwen_result.get('confidence', 0):.2f}"
                )
            else:
                logger.debug(f"[{call_id}] Qwen: No fraud detected")
            
            return qwen_result
            
        except Exception as e:
            logger.error(
                f"[{call_id}] Qwen detection error: {e}",
                exc_info=True
            )
            return None

    async def _run_tier2_llm(
        self,
        transcript: str,
        call_id: str,
        context: Dict,
        tier1_result: Dict
    ) -> Optional[Dict]:
        """
        Run Tier2 LLM analysis with fallback.
        
        Args:
            transcript: Call transcript
            call_id: Call ID
            context: Call context
            tier1_result: Tier1 detection result
            
        Returns:
            Tier2 result or None
        """
        # Try LLM first
        tier2_result = await self.tier2_llm.analyze(
            transcript=transcript,
            context=context,
            timeout=2.0
        )
        
        # Fallback if LLM not available
        if tier2_result is None:
            logger.debug(
                f"[{call_id}] Using Tier2 fallback "
                "(Ollama unavailable)"
            )
            tier2_result = self.tier2_fallback.analyze(
                transcript=transcript,
                tier1_result=tier1_result
            )
        
        return tier2_result

    def _create_alert(
        self,
        call_id: str,
        tier1_result: Optional[Dict] = None,
        tier2_result: Optional[Dict] = None,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        Create formatted alert for user.
        
        Args:
            call_id: Call identifier
            tier1_result: Result from Tier1 detection
            tier2_result: Result from Tier2 detection (overrides Tier1)
            context: Call context
            
        Returns:
            Alert dictionary
        """
        context = context or {}
        
        # Use Tier2 if available, otherwise Tier1
        result = tier2_result or tier1_result
        
        risk_score = result.get('score', result.get('risk_score', 0))
        risk_level = self._get_risk_level(risk_score)
        
        # Extract red flags
        red_flags = []
        
        if tier2_result:
            red_flags = tier2_result.get('red_flags', [])
        else:
            # Extract from Tier1
            if tier1_result.get('matched_keywords'):
                red_flags.append(
                    f"Known scam keywords: "
                    f"{', '.join([k[0] for k in tier1_result['matched_keywords'][:3]])}"
                )
            
            if tier1_result.get('matched_pattern'):
                red_flags.append(
                    tier1_result['matched_pattern'].get('description', '')
                )
        
        alert = {
            "alert_id": f"alert_{call_id}_{int(time.time())}",
            "call_id": call_id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "detection_tier": result.get('tier', 'unknown'),
            "message": self._format_message(risk_score),
            "red_flags": red_flags[:5],  # Limit to 5
            "recommended_action": self._get_recommended_action(risk_score),
            "timestamp": datetime.utcnow().isoformat(),
            "details": {
                "is_scam": result.get('is_scam', risk_score > 60),
                "reasoning": result.get(
                    'reasoning',
                    f"Risk score: {risk_score}/100"
                ),
                "confidence": result.get('confidence', 70),
                "caller_id": context.get('caller_id', 'Unknown'),
                "duration": context.get('duration', 0)
            }
        }
        
        return alert

    def _get_risk_level(self, score: int) -> str:
        """Determine risk level from score."""
        if score >= 85:
            return "high"
        elif score >= 50:
            return "medium"
        else:
            return "low"

    def _format_message(self, score: int) -> str:
        """Format alert message based on risk score."""
        if score >= 85:
            return "⚠️ SCAM DETECTED: This appears to be a fraudulent call"
        elif score >= 50:
            return "⚠️ FRAUD ALERT: This call shows signs of being a scam"
        else:
            return "ℹ️ Review: This call may be suspicious"

    def _get_recommended_action(self, score: int) -> str:
        """Get recommended action based on risk score."""
        if score >= 85:
            return (
                "🛑 HANG UP IMMEDIATELY\n"
                "• Do NOT share personal information\n"
                "• Do NOT send money or gift cards\n"
                "• Consider reporting to authorities"
            )
        elif score >= 50:
            return (
                "⚠️ BE CAUTIOUS\n"
                "• Verify caller's identity independently\n"
                "• Don't share sensitive information\n"
                "• Contact entity directly if requested"
            )
        else:
            return "Continue conversation but remain alert to any requests"

    async def _log_detection(
        self,
        call_id: str,
        transcript: str,
        tier1_result: Dict,
        alert: Optional[Dict],
        processing_time_ms: int
    ):
        """
        Log detection result to database.
        
        Args:
            call_id: Call ID
            transcript: Call transcript
            tier1_result: Tier1 result
            alert: Alert if created (can be None)
            processing_time_ms: Processing time
        """
        try:
            from sqlalchemy.orm import Session
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from backend.models import get_db_context
            from backend.models.database import DetectionLog
            
            with get_db_context() as db:
                log_entry = DetectionLog(
                    call_id=call_id,
                    transcript=transcript,
                    tier1_score=tier1_result.get('score'),
                    tier1_details={
                        "keyword_score": tier1_result.get('keyword_score'),
                        "pattern_score": tier1_result.get('pattern_score'),
                        "vector_score": tier1_result.get('vector_score'),
                        "matched_keywords": [
                            list(k) for k in 
                            tier1_result.get('matched_keywords', [])
                        ]
                    },
                    final_decision={
                        "alert_created": alert is not None,
                        "risk_level": alert.get('risk_level') if alert else None
                    },
                    processing_time_ms=processing_time_ms
                )
                
                db.add(log_entry)
                db.commit()
                
                logger.debug(f"[{call_id}] Detection logged (took {processing_time_ms}ms)")
        
        except Exception as e:
            logger.error(f"[{call_id}] Failed to log detection: {e}")
