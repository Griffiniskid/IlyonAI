"""
Session storage for web authentication.

Provides session management with Redis as primary storage
and PostgreSQL as fallback. Sessions are used for wallet-based
authentication in the web frontend.
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import json

from src.config import settings

logger = logging.getLogger(__name__)


class SessionStore:
    """
    Hybrid session storage with Redis primary and PostgreSQL fallback.
    
    Sessions store authenticated wallet addresses and their metadata.
    Redis is used for fast access with auto-expiry.
    PostgreSQL is used as fallback when Redis is unavailable.
    """
    
    def __init__(self):
        self._redis = None
        self._db = None
        self._initialized = False
        self._use_redis = False
    
    async def init(self):
        """Initialize session storage backends."""
        if self._initialized:
            return
        
        # Try to connect to Redis
        if settings.redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                # Test connection
                await self._redis.ping()
                self._use_redis = True
                logger.info("Session store: Redis connected")
            except Exception as e:
                logger.warning(f"Redis connection failed, using database fallback: {e}")
                self._redis = None
        
        # Get database reference for fallback
        try:
            from src.storage.database import get_database
            self._db = await get_database()
            if self._db._initialized:
                logger.info("Session store: PostgreSQL fallback ready")
        except Exception as e:
            logger.warning(f"Database fallback not available: {e}")
        
        self._initialized = True
    
    def _session_key(self, token: str) -> str:
        """Generate Redis key for session."""
        return f"session:{token}"
    
    async def create_session(
        self,
        wallet_address: str,
        ttl_seconds: int = None
    ) -> str:
        """
        Create a new session for a wallet.
        
        Args:
            wallet_address: Authenticated wallet address
            ttl_seconds: Session TTL in seconds (default: 24 hours)
            
        Returns:
            Session token string
        """
        await self.init()
        
        token = secrets.token_urlsafe(48)
        ttl = ttl_seconds or (settings.session_ttl_hours * 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        session_data = {
            "wallet": wallet_address,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_used": datetime.utcnow().isoformat()
        }
        
        # Try Redis first
        if self._use_redis and self._redis:
            try:
                await self._redis.setex(
                    self._session_key(token),
                    ttl,
                    json.dumps(session_data)
                )
                logger.debug(f"Session created in Redis for {wallet_address[:8]}...")
                return token
            except Exception as e:
                logger.warning(f"Redis session create failed: {e}")
        
        # Fallback to database
        if self._db and self._db._initialized:
            try:
                await self._db.create_user_session(
                    token=token,
                    wallet_address=wallet_address,
                    expires_at=expires_at
                )
                logger.debug(f"Session created in DB for {wallet_address[:8]}...")
                return token
            except Exception as e:
                logger.error(f"Database session create failed: {e}")
        
        # Ultimate fallback: return token anyway (will be validated in-memory)
        logger.warning("No persistent session storage available")
        return token
    
    async def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get session data by token.
        
        Args:
            token: Session token
            
        Returns:
            Session dict with 'wallet', 'created_at', 'expires_at' or None
        """
        await self.init()
        
        # Try Redis first
        if self._use_redis and self._redis:
            try:
                data = await self._redis.get(self._session_key(token))
                if data:
                    session = json.loads(data)
                    # Update last_used
                    session["last_used"] = datetime.utcnow().isoformat()
                    await self._redis.set(
                        self._session_key(token),
                        json.dumps(session),
                        keepttl=True
                    )
                    return session
            except Exception as e:
                logger.warning(f"Redis session get failed: {e}")
        
        # Fallback to database
        if self._db and self._db._initialized:
            try:
                session = await self._db.get_user_session(token)
                if session:
                    # Check expiry
                    if session.expires_at < datetime.utcnow():
                        await self.delete_session(token)
                        return None
                    # Update last_used
                    await self._db.update_session_last_used(token)
                    return {
                        "wallet": session.wallet_address,
                        "created_at": session.created_at.isoformat(),
                        "expires_at": session.expires_at.isoformat(),
                        "last_used": datetime.utcnow().isoformat()
                    }
            except Exception as e:
                logger.warning(f"Database session get failed: {e}")
        
        return None
    
    async def delete_session(self, token: str) -> bool:
        """
        Delete a session.
        
        Args:
            token: Session token to delete
            
        Returns:
            True if deleted successfully
        """
        await self.init()
        
        success = False
        
        # Delete from Redis
        if self._use_redis and self._redis:
            try:
                await self._redis.delete(self._session_key(token))
                success = True
            except Exception as e:
                logger.warning(f"Redis session delete failed: {e}")
        
        # Delete from database
        if self._db and self._db._initialized:
            try:
                await self._db.delete_user_session(token)
                success = True
            except Exception as e:
                logger.warning(f"Database session delete failed: {e}")
        
        return success
    
    async def extend_session(self, token: str, ttl_seconds: int = None) -> bool:
        """
        Extend session expiration.
        
        Args:
            token: Session token
            ttl_seconds: New TTL in seconds
            
        Returns:
            True if extended successfully
        """
        await self.init()
        
        ttl = ttl_seconds or (settings.session_ttl_hours * 3600)
        new_expires = datetime.utcnow() + timedelta(seconds=ttl)
        
        # Extend in Redis
        if self._use_redis and self._redis:
            try:
                data = await self._redis.get(self._session_key(token))
                if data:
                    session = json.loads(data)
                    session["expires_at"] = new_expires.isoformat()
                    session["last_used"] = datetime.utcnow().isoformat()
                    await self._redis.setex(
                        self._session_key(token),
                        ttl,
                        json.dumps(session)
                    )
                    return True
            except Exception as e:
                logger.warning(f"Redis session extend failed: {e}")
        
        # Extend in database
        if self._db and self._db._initialized:
            try:
                await self._db.extend_user_session(token, new_expires)
                return True
            except Exception as e:
                logger.warning(f"Database session extend failed: {e}")
        
        return False
    
    async def cleanup_expired(self) -> int:
        """
        Clean up expired sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        await self.init()
        
        count = 0
        
        # Redis handles expiry automatically, but clean database
        if self._db and self._db._initialized:
            try:
                count = await self._db.cleanup_expired_sessions()
                if count > 0:
                    logger.info(f"Cleaned up {count} expired sessions")
            except Exception as e:
                logger.warning(f"Session cleanup failed: {e}")
        
        return count
    
    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()
            self._redis = None
        self._initialized = False


# Global session store instance
_session_store: Optional[SessionStore] = None


async def get_session_store() -> SessionStore:
    """Get or create global session store instance."""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
        await _session_store.init()
    return _session_store
