"""
Wallet authentication API routes.

Implements Sign-In With Solana (SIWS) for wallet-based authentication.
"""

import logging
from aiohttp import web
from datetime import datetime, timedelta
from typing import Dict, Optional
import secrets
import hashlib
import base64

from src.api.schemas.responses import (
    AuthChallengeResponse, AuthVerifyResponse, UserProfileResponse, ErrorResponse
)
from src.api.schemas.requests import AuthChallengeRequest, AuthVerifyRequest
from src.config import settings

logger = logging.getLogger(__name__)

# In-memory storage (use Redis/DB in production)
_challenges: Dict[str, Dict] = {}  # challenge -> {wallet, expires, nonce}
_sessions: Dict[str, Dict] = {}    # session_token -> {wallet, expires}
_users: Dict[str, Dict] = {}       # wallet -> user data

CHALLENGE_TTL = 300  # 5 minutes
SESSION_TTL = 86400  # 24 hours


def generate_challenge() -> str:
    """Generate a random challenge string"""
    return secrets.token_hex(32)


def generate_session_token() -> str:
    """Generate a session token"""
    return secrets.token_urlsafe(48)


def create_sign_message(wallet: str, nonce: str) -> str:
    """Create the message to be signed by the wallet"""
    return f"""AI Sentinel Authentication

Wallet: {wallet}
Nonce: {nonce}
Timestamp: {datetime.utcnow().isoformat()}

Sign this message to authenticate with AI Sentinel.
This request will not trigger a blockchain transaction or cost any gas fees."""


def verify_solana_signature(message: str, signature: str, wallet: str) -> bool:
    """
    Verify a Solana signature.

    In production, use nacl or solana-py for proper Ed25519 verification.
    For now, we'll accept the signature as valid (demo mode).
    """
    # TODO: Implement proper Ed25519 signature verification
    # from nacl.signing import VerifyKey
    # from nacl.exceptions import BadSignatureError
    #
    # try:
    #     verify_key = VerifyKey(base58.b58decode(wallet))
    #     verify_key.verify(message.encode(), base58.b58decode(signature))
    #     return True
    # except BadSignatureError:
    #     return False

    # For demo: Accept if signature is at least 64 chars
    return len(signature) >= 64


def cleanup_expired():
    """Clean up expired challenges and sessions"""
    now = datetime.utcnow()

    # Clean challenges
    expired_challenges = [
        k for k, v in _challenges.items()
        if v['expires'] < now
    ]
    for k in expired_challenges:
        del _challenges[k]

    # Clean sessions
    expired_sessions = [
        k for k, v in _sessions.items()
        if v['expires'] < now
    ]
    for k in expired_sessions:
        del _sessions[k]


async def get_challenge(request: web.Request) -> web.Response:
    """
    POST /api/v1/auth/challenge

    Get a challenge for wallet authentication.
    The wallet must sign this challenge to prove ownership.
    """
    cleanup_expired()

    try:
        data = await request.json()
        req = AuthChallengeRequest(**data)
    except Exception as e:
        return web.json_response(
            ErrorResponse(error="Invalid request", code="INVALID_REQUEST").model_dump(mode='json'),
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
    cleanup_expired()

    try:
        data = await request.json()
        req = AuthVerifyRequest(**data)
    except Exception as e:
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

    # Verify signature
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

    # Create session
    session_token = generate_session_token()
    expires = datetime.utcnow() + timedelta(seconds=SESSION_TTL)

    _sessions[session_token] = {
        'wallet': req.wallet_address,
        'expires': expires,
        'created': datetime.utcnow()
    }

    # Create/update user
    if req.wallet_address not in _users:
        _users[req.wallet_address] = {
            'wallet': req.wallet_address,
            'created_at': datetime.utcnow(),
            'analyses_count': 0,
            'tracked_wallets': 0,
            'alerts_count': 0
        }

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
        if token in _sessions:
            del _sessions[token]
            logger.info("Session invalidated")

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
    session = _sessions.get(token)

    if not session:
        return web.json_response(
            ErrorResponse(error="Invalid session", code="INVALID_SESSION").model_dump(mode='json'),
            status=401
        )

    if session['expires'] < datetime.utcnow():
        del _sessions[token]
        return web.json_response(
            ErrorResponse(error="Session expired", code="SESSION_EXPIRED").model_dump(mode='json'),
            status=401
        )

    wallet = session['wallet']
    user = _users.get(wallet, {})

    response = UserProfileResponse(
        wallet_address=wallet,
        created_at=user.get('created_at', datetime.utcnow()),
        analyses_count=user.get('analyses_count', 0),
        tracked_wallets=user.get('tracked_wallets', 0),
        alerts_count=user.get('alerts_count', 0),
        premium_until=user.get('premium_until')
    ).model_dump(mode='json')

    return web.json_response(response)


@web.middleware
async def auth_middleware(request: web.Request, handler):
    """
    Middleware to extract user from session token.
    Sets request['user_id'] if authenticated.
    """
    auth_header = request.headers.get('Authorization', '')

    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        session = _sessions.get(token)

        if session and session['expires'] >= datetime.utcnow():
            request['user_id'] = session['wallet']

    return await handler(request)


def setup_auth_routes(app: web.Application):
    """Setup authentication API routes"""
    app.router.add_post('/api/v1/auth/challenge', get_challenge)
    app.router.add_post('/api/v1/auth/verify', verify_challenge)
    app.router.add_post('/api/v1/auth/logout', logout)
    app.router.add_get('/api/v1/auth/me', get_me)

    # Add auth middleware
    app.middlewares.append(auth_middleware)

    logger.info("Auth routes registered")
