"""
Wallet authentication API routes.

Implements Sign-In With Solana (SIWS) for wallet-based authentication.
Uses proper Ed25519 signature verification with pynacl.
"""

import logging
from aiohttp import web
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable
import secrets
import base64
import functools

# Cryptography for signature verification
import base58
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

from src.api.schemas.responses import (
    AuthChallengeResponse, AuthVerifyResponse, UserProfileResponse, ErrorResponse
)
from src.api.schemas.requests import AuthChallengeRequest, AuthVerifyRequest
from src.config import settings

logger = logging.getLogger(__name__)

# In-memory challenge storage (challenges are short-lived, Redis not needed)
_challenges: Dict[str, Dict] = {}

CHALLENGE_TTL = 300  # 5 minutes


async def get_session_store():
    from src.storage.sessions import get_session_store as _get_session_store

    return await _get_session_store()


def generate_challenge() -> str:
    """Generate a random challenge string."""
    return secrets.token_hex(32)


def create_sign_message(wallet: str, nonce: str) -> str:
    """Create the message to be signed by the wallet."""
    return f"""Ilyon AI Authentication

Wallet: {wallet}
Nonce: {nonce}
Timestamp: {datetime.utcnow().isoformat()}

Sign this message to authenticate with Ilyon AI.
This request will not trigger a blockchain transaction or cost any gas fees."""


def verify_solana_signature(message: str, signature_base64: str, wallet_address: str) -> bool:
    """
    Verify a Solana wallet signature using Ed25519.
    
    Args:
        message: The original message that was signed
        signature_base64: Base64-encoded signature from wallet
        wallet_address: Solana wallet public key (base58)
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Decode wallet public key from base58
        public_key_bytes = base58.b58decode(wallet_address)
        
        # Validate public key length (32 bytes for Ed25519)
        if len(public_key_bytes) != 32:
            logger.warning(f"Invalid public key length: {len(public_key_bytes)}")
            return False
        
        # Create verify key from public key bytes
        verify_key = VerifyKey(public_key_bytes)
        
        # Decode signature from base64
        signature_bytes = base64.b64decode(signature_base64)
        
        # Validate signature length (64 bytes for Ed25519)
        if len(signature_bytes) != 64:
            logger.warning(f"Invalid signature length: {len(signature_bytes)}")
            return False
        
        # Encode message to bytes
        message_bytes = message.encode('utf-8')
        
        # Verify signature (raises BadSignatureError if invalid)
        verify_key.verify(message_bytes, signature_bytes)
        
        logger.info(f"Signature verified for wallet {wallet_address[:8]}...")
        return True
        
    except BadSignatureError:
        logger.warning(f"Invalid signature for wallet {wallet_address[:8]}...")
        return False
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False


def cleanup_expired_challenges():
    """Clean up expired challenges."""
    now = datetime.utcnow()
    expired = [k for k, v in _challenges.items() if v['expires'] < now]
    for k in expired:
        del _challenges[k]


# ═══════════════════════════════════════════════════════════════════════════════
# PROTECTED ROUTE DECORATOR
# ═══════════════════════════════════════════════════════════════════════════════

def require_auth(handler: Callable) -> Callable:
    """
    Decorator to require authentication for a route.
    
    Sets request['user_wallet'] to the authenticated wallet address.
    Returns 401 if not authenticated.
    """
    @functools.wraps(handler)
    async def wrapper(request: web.Request) -> web.Response:
        # Check if user was authenticated by middleware
        if 'user_wallet' not in request:
            return web.json_response(
                ErrorResponse(
                    error="Authentication required",
                    code="AUTH_REQUIRED"
                ).model_dump(mode='json'),
                status=401
            )
        return await handler(request)
    return wrapper


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

async def get_challenge(request: web.Request) -> web.Response:
    """
    POST /api/v1/auth/challenge
    
    Get a challenge for wallet authentication.
    The wallet must sign this challenge to prove ownership.
    """
    cleanup_expired_challenges()

    try:
        data = await request.json()
        req = AuthChallengeRequest(**data)
    except Exception as e:
        logger.warning(f"Invalid challenge request: {e}")
        return web.json_response(
            ErrorResponse(error="Invalid request", code="INVALID_REQUEST").model_dump(mode='json'),
            status=400
        )

    # Validate wallet address format
    try:
        decoded = base58.b58decode(req.wallet_address)
        if len(decoded) != 32:
            raise ValueError("Invalid length")
    except Exception:
        return web.json_response(
            ErrorResponse(error="Invalid wallet address", code="INVALID_WALLET").model_dump(mode='json'),
            status=400
        )

    # Generate challenge
    nonce = generate_challenge()
    message = create_sign_message(req.wallet_address, nonce)
    expires = datetime.utcnow() + timedelta(seconds=CHALLENGE_TTL)

    # Store challenge
    _challenges[nonce] = {
        'wallet': req.wallet_address,
        'expires': expires,
        'message': message
    }

    response = AuthChallengeResponse(
        challenge=nonce,
        expires_at=expires,
        message=message
    ).model_dump(mode='json')

    logger.info(f"Auth challenge created for {req.wallet_address[:8]}...")

    return web.json_response(response)


async def verify_challenge(request: web.Request) -> web.Response:
    """
    POST /api/v1/auth/verify
    
    Verify a signed challenge and create a session.
    """
    cleanup_expired_challenges()

    try:
        data = await request.json()
        req = AuthVerifyRequest(**data)
    except Exception as e:
        logger.warning(f"Invalid verify request: {e}")
        return web.json_response(
            ErrorResponse(error="Invalid request", code="INVALID_REQUEST").model_dump(mode='json'),
            status=400
        )

    # Find challenge
    challenge_data = _challenges.get(req.challenge)

    if not challenge_data:
        return web.json_response(
            ErrorResponse(error="Challenge not found or expired", code="INVALID_CHALLENGE").model_dump(mode='json'),
            status=400
        )

    # Verify wallet matches
    if challenge_data['wallet'] != req.wallet_address:
        return web.json_response(
            ErrorResponse(error="Wallet mismatch", code="WALLET_MISMATCH").model_dump(mode='json'),
            status=400
        )

    # Check expiry
    if challenge_data['expires'] < datetime.utcnow():
        del _challenges[req.challenge]
        return web.json_response(
            ErrorResponse(error="Challenge expired", code="CHALLENGE_EXPIRED").model_dump(mode='json'),
            status=400
        )

    # Verify signature using Ed25519
    if not verify_solana_signature(
        challenge_data['message'],
        req.signature,
        req.wallet_address
    ):
        return web.json_response(
            ErrorResponse(error="Invalid signature", code="INVALID_SIGNATURE").model_dump(mode='json'),
            status=401
        )

    # Delete used challenge
    del _challenges[req.challenge]

    # Create session using session store
    try:
        session_store = await get_session_store()
        session_token = await session_store.create_session(req.wallet_address)
        expires = datetime.utcnow() + timedelta(hours=settings.session_ttl_hours)
    except Exception as e:
        logger.error(f"Session creation failed: {e}")
        # Fallback: generate token but it won't be persisted
        session_token = secrets.token_urlsafe(48)
        expires = datetime.utcnow() + timedelta(hours=24)

    # Create/update user in database
    try:
        from src.storage.database import get_database
        db = await get_database()
        await db.get_or_create_web_user(req.wallet_address)
    except Exception as e:
        logger.warning(f"User creation failed (non-critical): {e}")

    response = AuthVerifyResponse(
        success=True,
        wallet_address=req.wallet_address,
        session_token=session_token,
        expires_at=expires
    ).model_dump(mode='json')

    logger.info(f"Auth successful for {req.wallet_address[:8]}...")

    return web.json_response(response)


async def logout(request: web.Request) -> web.Response:
    """
    POST /api/v1/auth/logout
    
    Invalidate the current session.
    """
    auth_header = request.headers.get('Authorization', '')

    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        try:
            session_store = await get_session_store()
            await session_store.delete_session(token)
            logger.info("Session invalidated")
        except Exception as e:
            logger.warning(f"Session deletion failed: {e}")

    return web.Response(status=204)


async def get_me(request: web.Request) -> web.Response:
    """
    GET /api/v1/auth/me
    
    Get current user profile.
    """
    auth_header = request.headers.get('Authorization', '')

    if not auth_header.startswith('Bearer '):
        return web.json_response(
            ErrorResponse(error="Authentication required", code="AUTH_REQUIRED").model_dump(mode='json'),
            status=401
        )

    token = auth_header[7:]
    
    # Get session
    try:
        session_store = await get_session_store()
        session = await session_store.get_session(token)
    except Exception as e:
        logger.error(f"Session lookup failed: {e}")
        session = None

    if not session:
        return web.json_response(
            ErrorResponse(error="Invalid session", code="INVALID_SESSION").model_dump(mode='json'),
            status=401
        )

    wallet = session['wallet']

    # Get user data from database
    user_data = {
        'wallet_address': wallet,
        'created_at': datetime.utcnow(),
        'analyses_count': 0,
        'tracked_wallets': 0,
        'alerts_count': 0,
        'premium_until': None
    }

    try:
        from src.storage.database import get_database
        db = await get_database()
        user = await db.get_web_user(wallet)
        if user:
            user_data = {
                'wallet_address': user.wallet_address,
                'created_at': user.created_at,
                'analyses_count': user.analyses_count or 0,
                'tracked_wallets': user.tracked_wallets_count or 0,
                'alerts_count': user.alerts_count or 0,
                'premium_until': user.premium_until
            }
    except Exception as e:
        logger.warning(f"User lookup failed (using defaults): {e}")

    response = UserProfileResponse(
        wallet_address=user_data['wallet_address'],
        created_at=user_data['created_at'],
        analyses_count=user_data['analyses_count'],
        tracked_wallets=user_data['tracked_wallets'],
        alerts_count=user_data['alerts_count'],
        premium_until=user_data['premium_until']
    ).model_dump(mode='json')

    return web.json_response(response)


async def refresh_session(request: web.Request) -> web.Response:
    """
    POST /api/v1/auth/refresh
    
    Refresh/extend the current session.
    """
    auth_header = request.headers.get('Authorization', '')

    if not auth_header.startswith('Bearer '):
        return web.json_response(
            ErrorResponse(error="Authentication required", code="AUTH_REQUIRED").model_dump(mode='json'),
            status=401
        )

    token = auth_header[7:]
    
    try:
        session_store = await get_session_store()
        success = await session_store.extend_session(token)
        
        if success:
            session = await session_store.get_session(token)
            if session:
                return web.json_response({
                    "success": True,
                    "expires_at": session.get('expires_at')
                })
    except Exception as e:
        logger.error(f"Session refresh failed: {e}")

    return web.json_response(
        ErrorResponse(error="Session refresh failed", code="REFRESH_FAILED").model_dump(mode='json'),
        status=400
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════════

@web.middleware
async def auth_middleware(request: web.Request, handler):
    """
    Middleware to extract user from session token.
    Sets request['user_wallet'] if authenticated.
    """
    auth_header = request.headers.get('Authorization', '')

    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        try:
            session_store = await get_session_store()
            session = await session_store.get_session(token)
            
            if session:
                request['user_wallet'] = session['wallet']
        except Exception as e:
            logger.debug(f"Auth middleware error: {e}")

    return await handler(request)


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTE SETUP
# ═══════════════════════════════════════════════════════════════════════════════

def setup_auth_routes(app: web.Application):
    """Setup authentication API routes."""
    app.router.add_post('/api/v1/auth/challenge', get_challenge)
    app.router.add_post('/api/v1/auth/verify', verify_challenge)
    app.router.add_post('/api/v1/auth/logout', logout)
    app.router.add_post('/api/v1/auth/refresh', refresh_session)
    app.router.add_get('/api/v1/auth/me', get_me)

    # Add auth middleware
    logger.info("Auth routes registered with Ed25519 signature verification")
