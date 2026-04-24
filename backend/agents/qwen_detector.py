"""Qwen-based ML fraud detector for phone call analysis."""
import torch
import json
import re
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class QwenFraudDetector:
    """
    ML-based fraud detection using DistilGPT2 language model (~350MB).
    Uses language model to analyze conversation context and patterns.
    """
    
    def __init__(self, model_name: str = "distilgpt2", use_local: bool = False):
        """
        Initialize Qwen fraud detector.
        
        Args:
            model_name: Hugging Face model identifier
            use_local: If True, load from local ./models/ directory
        """
        self.model_name = model_name
        self.use_local = use_local
        self.model = None
        self.tokenizer = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        logger.info(f"Initializing Qwen detector on device: {self.device}")
        
        # Lazy loading - only load model when first needed
        self._initialized = False
    
    def _initialize_model(self):
        """Lazy load the model on first use"""
        if self._initialized:
            return
        
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            
            model_path = f"./models/{self.model_name}" if self.use_local else self.model_name
            
            logger.info(f"Loading Qwen model from: {model_path}")
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True
            )
            
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                device_map="auto" if self.device == "cuda" else None,
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                low_cpu_mem_usage=True
            )
            
            if self.device == "cpu":
                self.model = self.model.to(self.device)
            
            self.model.eval()
            self._initialized = True
            
            logger.info("✅ Qwen model loaded successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to load Qwen model: {e}")
            self._initialized = False
            raise
    
    async def detect(self, transcript: str, call_id: str, context: Dict[str, Any]) -> Optional[Dict]:
        """
        Detect fraud in phone call transcript using Qwen model.
        
        Args:
            transcript: Full conversation text
            call_id: Unique call identifier
            context: Additional metadata (duration, caller_id, phone_number, etc.)
        
        Returns:
            Alert dictionary if fraud detected, None otherwise
        """
        try:
            # Initialize model on first use
            if not self._initialized:
                self._initialize_model()
            
            # Build detection prompt
            prompt = self._build_prompt(transcript, context)
            
            # Generate fraud analysis
            response = await self._generate_analysis(prompt)
            
            # Parse and format result
            result = self._parse_response(response, call_id, transcript)
            
            if result:
                logger.info(f"[{call_id}] 🤖 Qwen detected fraud: Risk={result['risk_score']}/100, Type={result.get('fraud_type', 'unknown')}")
            else:
                logger.info(f"[{call_id}] ✅ Qwen: No fraud detected")
            
            return result
            
        except Exception as e:
            logger.error(f"[{call_id}] Qwen detection error: {e}", exc_info=True)
            # Return None so system falls back to keyword detection
            return None
    
    def _build_prompt(self, transcript: str, context: Dict[str, Any]) -> str:
        """Build analysis prompt for Qwen model"""
        
        duration = context.get('duration_seconds', 'unknown')
        caller_id = context.get('caller_id', 'unknown')
        phone_number = context.get('phone_number', 'unknown')
        
        prompt = f"""You are an expert fraud detection AI analyzing phone conversations. Analyze the following call for fraud indicators.

CONVERSATION TRANSCRIPT:
{transcript}

CALL METADATA:
- Duration: {duration} seconds
- Caller ID: {caller_id}
- Phone Number: {phone_number}

FRAUD INDICATORS TO CHECK:
1. Impersonation: Government agencies (IRS, FBI, Social Security), banks, tech support
2. Urgency: "Act immediately", "within 24 hours", "right now"
3. Threats: Arrest, account closure, legal action, deportation
4. Payment requests: Gift cards, wire transfer, cryptocurrency, prepaid cards
5. Information requests: SSN, passwords, account numbers, personal details
6. Too-good-to-be-true: Prizes, refunds, loans, investments
7. Caller behavior: Aggressive, evasive, scripted, pressure tactics

ANALYSIS TASK:
Provide a detailed fraud assessment in JSON format:

{{
  "is_fraud": true or false,
  "risk_score": integer from 0-100,
  "risk_level": "low" or "medium" or "high",
  "fraud_type": "government_impersonation" or "tech_support" or "prize_scam" or "phishing" or "other" or "none",
  "red_flags": ["list of specific fraud indicators found"],
  "confidence": decimal from 0.0 to 1.0,
  "explanation": "brief 1-2 sentence explanation of your decision"
}}

YOUR ANALYSIS:"""
        
        return prompt
    
    async def _generate_analysis(self, prompt: str) -> str:
        """Generate fraud analysis using Qwen model"""
        
        # Tokenize input
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=2048
        ).to(self.device)
        
        # Generate response
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.3,  # Lower temperature for more consistent output
                do_sample=True,
                top_p=0.9,
                repetition_penalty=1.1,
                pad_token_id=self.tokenizer.eos_token_id
            )
        
        # Decode response
        full_response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Extract only the generated part (after the prompt)
        response = full_response[len(prompt):].strip()
        
        return response
    
    def _parse_response(self, response: str, call_id: str, transcript: str) -> Optional[Dict]:
        """Parse Qwen model response into alert format"""
        
        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        
        if not json_match:
            logger.warning(f"[{call_id}] Could not extract JSON from Qwen response")
            return None
        
        try:
            result = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning(f"[{call_id}] Failed to parse JSON: {e}")
            return None
        
        # Check if fraud detected
        is_fraud = result.get('is_fraud', False)
        risk_score = result.get('risk_score', 0)
        
        if not is_fraud or risk_score < 50:
            return None
        
        # Extract fields with defaults
        fraud_type = result.get('fraud_type', 'unknown')
        risk_level = result.get('risk_level', 'medium')
        red_flags = result.get('red_flags', [])
        confidence = result.get('confidence', 0.7)
        explanation = result.get('explanation', 'Fraud indicators detected')
        
        # Format as standardized alert
        return {
            "alert_id": f"alert_{uuid.uuid4().hex[:12]}",
            "call_id": call_id,
            "risk_score": min(risk_score, 100),
            "risk_level": risk_level,
            "detection_tier": "qwen_ml",
            "fraud_type": fraud_type,
            "confidence": float(confidence),
            "message": f"🤖 AI Model: {fraud_type.replace('_', ' ').title()} detected (Confidence: {confidence*100:.0f}%)",
            "red_flags": red_flags if isinstance(red_flags, list) else [],
            "explanation": explanation,
            "recommended_action": self._get_action(risk_level),
            "timestamp": datetime.utcnow().isoformat(),
            "model_version": "Qwen-0.5B-v1",
            "alert_metadata": {
                "model_name": self.model_name,
                "detection_method": "llm_analysis"
            }
        }
    
    def _get_action(self, risk_level: str) -> str:
        """Get recommended action based on risk level"""
        actions = {
            "low": "Monitor call - review if escalates",
            "medium": "Review transcript and consider intervention",
            "high": "⚠️ IMMEDIATE ACTION: Warn recipient, block caller"
        }
        return actions.get(risk_level, "Review manually")
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information and status"""
        return {
            "model_name": self.model_name,
            "initialized": self._initialized,
            "device": self.device,
            "cuda_available": torch.cuda.is_available()
        }
