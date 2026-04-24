"""Redis client and connection management with in-memory fallback."""
import sys
from pathlib import Path
import json
from typing import Optional, Any, Dict
import logging
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import settings

logger = logging.getLogger(__name__)

# In-memory storage fallback (when Redis unavailable)
_memory_store: Dict[str, Any] = {}
_session_expiry: Dict[str, datetime] = {}
_use_redis = True  # Try Redis first, fallback to memory if unavailable


class RedisClient:
    """Async Redis client wrapper with fallback."""

    _instance: Optional[Any] = None

    @classmethod
    async def get_instance(cls):
        """Get or create Redis connection."""
        global _use_redis
        
        if not _use_redis:
            return None
            
        if cls._instance is None:
            try:
                import redis.asyncio as redis
                cls._instance = await redis.from_url(
                    settings.redis_url,
                    encoding="utf8",
                    decode_responses=True
                )
                # Test connection
                await cls._instance.ping()
                logger.info("✅ Redis connection established")
            except Exception as e:
                logger.warning(f"⚠️ Redis unavailable, using in-memory storage: {e}")
                _use_redis = False
                cls._instance = None
        return cls._instance

    @classmethod
    async def close(cls):
        """Close Redis connection."""
        if cls._instance:
            await cls._instance.close()
            cls._instance = None
            logger.info("Redis connection closed")


async def get_redis():
    """Get Redis connection (or None if using memory)."""
    return await RedisClient.get_instance()


async def set_call_session(
    call_id: str,
    data: dict,
    expire_seconds: int = 3600
) -> bool:
    """Store call session (Redis or in-memory)."""
    redis_client = await get_redis()
    key = f"call:{call_id}"
    
    try:
        if redis_client:
            # Use Redis
            await redis_client.set(
                key,
                json.dumps(data),
                ex=expire_seconds
            )
        else:
            # Use in-memory fallback
            _memory_store[key] = data
            _session_expiry[key] = datetime.utcnow() + timedelta(seconds=expire_seconds)
        return True
    except Exception as e:
        logger.error(f"Failed to set call session: {e}")
        # Fallback to memory if Redis fails
        _memory_store[key] = data
        _session_expiry[key] = datetime.utcnow() + timedelta(seconds=expire_seconds)
        return True


async def get_call_session(call_id: str) -> Optional[dict]:
    """Retrieve call session (Redis or in-memory)."""
    redis_client = await get_redis()
    key = f"call:{call_id}"
    
    try:
        if redis_client:
            # Use Redis
            data = await redis_client.get(key)
            if data:
                return json.loads(data)
        else:
            # Use in-memory fallback
            if key in _memory_store:
                # Check expiry
                if key in _session_expiry and datetime.utcnow() < _session_expiry[key]:
                    return _memory_store[key]
                else:
                    # Expired - clean up
                    _memory_store.pop(key, None)
                    _session_expiry.pop(key, None)
        return None
    except Exception as e:
        logger.error(f"Failed to get call session: {e}")
        # Try memory fallback
        return _memory_store.get(key)


async def update_call_session(call_id: str, updates: dict) -> bool:
    """Update call session (Redis or in-memory)."""
    session = await get_call_session(call_id)
    if session:
        session.update(updates)
        return await set_call_session(call_id, session)
    return False


async def delete_call_session(call_id: str) -> bool:
    """Delete call session (Redis or in-memory)."""
    redis_client = await get_redis()
    key = f"call:{call_id}"
    
    try:
        if redis_client:
            await redis_client.delete(key)
        else:
            _memory_store.pop(key, None)
            _session_expiry.pop(key, None)
        return True
    except Exception as e:
        logger.error(f"Failed to delete call session: {e}")
        return False


async def publish_alert(alert_data: dict) -> bool:
    """Publish alert to Redis pub/sub (or log if Redis unavailable)."""
    redis_client = await get_redis()
    try:
        if redis_client:
            await redis_client.publish(
                "fraud_alerts",
                json.dumps(alert_data)
            )
            return True
        else:
            # No Redis, just log the alert
            logger.info(f"Alert (no Redis pub/sub): {alert_data.get('alert_id', 'unknown')}")
            return True
    except Exception as e:
        logger.warning(f"Failed to publish alert (non-critical): {e}")
        return True  # Don't fail the whole operation
