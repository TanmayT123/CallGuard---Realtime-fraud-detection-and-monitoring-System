"""Tier 1 fast fraud detection using patterns and keywords."""
import re
import logging
import asyncio
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class KeywordMatcher:
    """Detect fraud using keyword matching."""

    # Scam keywords with risk scores
    SCAM_KEYWORDS = {
        # Urgency tactics (15-20 points)
        "urgent": 15,
        "immediately": 15,
        "right now": 20,
        "limited time": 20,
        "expire": 15,
        "expired": 20,
        "hurry": 15,
        "quickly": 10,
        "asap": 20,
        
        # Account threats (20-30 points)
        "suspended": 25,
        "locked": 25,
        "frozen": 25,
        "closed": 20,
        "deactivated": 25,
        "disabled": 20,
        "compromised": 30,
        "unauthorized": 20,
        "unusual activity": 25,
        "suspicious activity": 25,
        
        # Authority impersonation (30-50 points)
        "irs": 40,
        "social security": 35,
        "fbi": 45,
        "police": 30,
        "government": 30,
        "federal": 30,
        "microsoft": 35,
        "apple": 30,
        "amazon": 25,
        "bank": 25,
        "paypal": 25,
        
        # Payment demands (40-50 points)
        "gift card": 50,
        "wire transfer": 45,
        "bitcoin": 40,
        "cryptocurrency": 40,
        "prepaid card": 45,
        "money transfer": 40,
        "payment": 20,
        "google play": 40,
        "itunes": 40,
        
        # Information requests (25-50 points)
        "verify account": 30,
        "confirm identity": 25,
        "social security number": 50,
        "ssn": 50,
        "bank account": 35,
        "credit card": 35,
        "card number": 40,
        "password": 40,
        "pin number": 45,
        "date of birth": 25,
        "mother's maiden name": 30,
        "security question": 20,
    }

    def __init__(self):
        """Initialize keyword matcher."""
        self.keywords = self.SCAM_KEYWORDS

    def score(self, text: str) -> int:
        """
        Score text based on scam keywords.
        
        Args:
            text: Text to analyze
            
        Returns:
            Risk score (0-100)
        """
        score = 0
        text_lower = text.lower()
        
        for keyword, weight in self.keywords.items():
            if keyword in text_lower:
                score += weight
        
        # Cap at 100
        return min(score, 100)

    def get_matched_keywords(self, text: str) -> List[Tuple[str, int]]:
        """
        Get all matched keywords and their scores.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of (keyword, weight) tuples
        """
        matched = []
        text_lower = text.lower()
        
        for keyword, weight in self.keywords.items():
            if keyword in text_lower:
                matched.append((keyword, weight))
        
        return matched


class PatternMatcher:
    """Detect fraud using predefined patterns."""

    SCAM_PATTERNS = [
        {
            "id": "fake_irs",
            "name": "Fake IRS Call",
            "keywords": ["irs", "tax", "refund", "arrest", "penalty"],
            "min_keywords": 2,
            "score": 90,
            "description": "Scammer impersonating IRS threatening legal action"
        },
        {
            "id": "tech_support",
            "name": "Tech Support Scam",
            "keywords": ["computer", "virus", "malware", "microsoft", "windows", "refund"],
            "min_keywords": 2,
            "score": 85,
            "description": "Fake tech support pretending to fix computer"
        },
        {
            "id": "account_suspension",
            "name": "Account Suspension Phishing",
            "keywords": ["account", "suspended", "verify", "confirm", "click", "link"],
            "min_keywords": 2,
            "score": 80,
            "description": "False account suspension to extract credentials"
        },
        {
            "id": "ssn_scam",
            "name": "Social Security Number Scam",
            "keywords": ["social security", "ssn", "number", "suspend", "arrest"],
            "min_keywords": 2,
            "score": 95,
            "description": "Threatening loss of SSN benefits"
        },
        {
            "id": "lottery_scam",
            "name": "Lottery/Prize Scam",
            "keywords": ["lottery", "winner", "prize", "congratulations", "claim", "fee"],
            "min_keywords": 2,
            "score": 85,
            "description": "False lottery/prize notification"
        },
        {
            "id": "grandparent_scam",
            "name": "Grandparent Scam",
            "keywords": ["grandpa", "grandma", "help", "money", "wire", "emergency"],
            "min_keywords": 2,
            "score": 80,
            "description": "Impersonating elderly relative in distress"
        },
        {
            "id": "amazon_scam",
            "name": "Amazon/Package Scam",
            "keywords": ["amazon", "package", "order", "delivery", "confirm", "billing"],
            "min_keywords": 2,
            "score": 75,
            "description": "Fake Amazon/package delivery notification"
        },
        {
            "id": "bank_scam",
            "name": "Bank Security Scam",
            "keywords": ["bank", "account", "security", "fraud", "verify", "confirm"],
            "min_keywords": 2,
            "score": 80,
            "description": "Pretending to be bank requesting verification"
        },
    ]

    def __init__(self):
        """Initialize pattern matcher."""
        self.patterns = self.SCAM_PATTERNS

    def score(self, text: str) -> Tuple[int, Optional[Dict]]:
        """
        Score text against known patterns.
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (score, matched_pattern)
        """
        text_lower = text.lower()
        
        for pattern in self.patterns:
            # Count keyword matches
            found_keywords = sum(
                1 for kw in pattern["keywords"] 
                if kw in text_lower
            )
            
            # Check if meets minimum threshold
            if found_keywords >= pattern["min_keywords"]:
                return pattern["score"], pattern
        
        return 0, None

    def get_all_matches(self, text: str) -> List[Dict]:
        """
        Get all matching patterns.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of matched patterns
        """
        text_lower = text.lower()
        matches = []
        
        for pattern in self.patterns:
            found_keywords = sum(
                1 for kw in pattern["keywords"] 
                if kw in text_lower
            )
            
            if found_keywords >= pattern["min_keywords"]:
                matches.append({
                    **pattern,
                    "found_keywords": found_keywords
                })
        
        return matches


class VectorMatcher:
    """Detect fraud using semantic similarity with ChromaDB."""

    def __init__(self):
        """Initialize vector matcher."""
        self.enabled = False
        self.client = None
        self.collection = None
        self.model = None
        
        try:
            self._initialize()
        except Exception as e:
            logger.warning(f"Vector matching not available: {e}")

    def _initialize(self):
        """Initialize ChromaDB and embedding model."""
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
            
            # Initialize embeddings model
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Initialize ChromaDB client
            self.client = chromadb.Client()
            
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name="scam_patterns",
                metadata={"description": "Known scam patterns"}
            )
            
            self.enabled = True
            logger.info("Vector matching initialized")
        
        except ImportError:
            logger.warning("chromadb or sentence-transformers not installed")
        except Exception as e:
            logger.warning(f"Failed to initialize vector matching: {e}")

    def add_pattern(self, text: str, metadata: Dict) -> bool:
        """
        Add a scam pattern to the vector database.
        
        Args:
            text: Pattern text
            metadata: Pattern metadata including risk_score
            
        Returns:
            True if successful
        """
        if not self.enabled or self.model is None:
            return False
        
        try:
            embedding = self.model.encode(text).tolist()
            
            self.collection.add(
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata],
                ids=[metadata.get('pattern_id', str(hash(text)))]
            )
            
            return True
        except Exception as e:
            logger.error(f"Failed to add pattern: {e}")
            return False

    def score(self, text: str, threshold: float = 0.3) -> Tuple[int, Optional[Dict]]:
        """
        Score text against known patterns using semantic similarity.
        
        Args:
            text: Text to analyze
            threshold: Similarity threshold (lower = more similar)
            
        Returns:
            Tuple of (score, matched_pattern)
        """
        if not self.enabled or self.model is None:
            return 0, None
        
        try:
            embedding = self.model.encode(text).tolist()
            
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=1
            )
            
            if not results['ids'] or not results['ids'][0]:
                return 0, None
            
            distance = results['distances'][0][0]
            
            # Check if similarity exceeds threshold
            if distance < threshold:
                matched = {
                    "text": results['documents'][0][0],
                    "metadata": results['metadatas'][0][0],
                    "similarity": 1 - distance,
                    "risk_score": results['metadatas'][0][0].get('risk_score', 75)
                }
                return matched['risk_score'], matched
        
        except Exception as e:
            logger.debug(f"Vector similarity search failed: {e}")
        
        return 0, None

    def seed_patterns(self) -> bool:
        """
        Seed database with initial scam patterns.
        
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        patterns = [
            {
                "text": "Your account has been suspended, verify now",
                "metadata": {
                    "pattern_id": "vector_account_susp_1",
                    "risk_score": 85,
                    "scam_type": "Account Phishing"
                }
            },
            {
                "text": "IRS calling about back taxes and potential arrest",
                "metadata": {
                    "pattern_id": "vector_irs_1",
                    "risk_score": 95,
                    "scam_type": "Government Impersonation"
                }
            },
            {
                "text": "We detected unusual activity on your account",
                "metadata": {
                    "pattern_id": "vector_unusual_activity_1",
                    "risk_score": 80,
                    "scam_type": "Account Fraud"
                }
            },
            {
                "text": "technical support to fix virus on your computer",
                "metadata": {
                    "pattern_id": "vector_tech_support_1",
                    "risk_score": 85,
                    "scam_type": "Tech Support Scam"
                }
            },
        ]
        
        success_count = 0
        for pattern in patterns:
            if self.add_pattern(pattern['text'], pattern['metadata']):
                success_count += 1
        
        logger.info(f"Seeded {success_count}/{len(patterns)} patterns")
        return success_count > 0


class Tier1Detector:
    """
    Tier 1 rapid fraud detection.
    
    Uses three parallel detection methods:
    1. Keyword matching (<10ms)
    2. Pattern rules (<20ms)
    3. Vector similarity (<50ms)
    
    Total time: <100ms
    """

    def __init__(self):
        """Initialize Tier 1 detector."""
        self.keyword_matcher = KeywordMatcher()
        self.pattern_matcher = PatternMatcher()
        self.vector_matcher = VectorMatcher()
        
        # Seed vector database with initial patterns
        if self.vector_matcher.enabled:
            self.vector_matcher.seed_patterns()

    async def detect(self, text: str) -> Dict:
        """
        Run Tier 1 detection in parallel.
        
        Args:
            text: Transcribed text to analyze
            
        Returns:
            Dictionary with:
                - score: Final risk score (0-100)
                - keyword_score: Keyword matching score
                - pattern_score: Pattern matching score
                - vector_score: Vector similarity score
                - matched_keywords: List of matched keywords
                - matched_pattern: Matched pattern details
                - matched_vector: Matched vector details
                - tier: "tier1"
        """
        # Run detection methods in parallel
        keyword_score = await asyncio.to_thread(
            self.keyword_matcher.score, 
            text
        )
        
        pattern_score, matched_pattern = await asyncio.to_thread(
            self.pattern_matcher.score, 
            text
        )
        
        vector_score, matched_vector = await asyncio.to_thread(
            self.vector_matcher.score, 
            text
        )
        
        # Get matched keywords
        matched_keywords = await asyncio.to_thread(
            self.keyword_matcher.get_matched_keywords, 
            text
        )
        
        # Final score is the maximum of all methods
        final_score = max(keyword_score, pattern_score, vector_score)
        
        return {
            "score": final_score,
            "keyword_score": keyword_score,
            "pattern_score": pattern_score,
            "vector_score": vector_score,
            "matched_keywords": matched_keywords,
            "matched_pattern": matched_pattern,
            "matched_vector": matched_vector,
            "tier": "tier1"
        }
