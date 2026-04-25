import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import base64

import bcrypt as _bcrypt
from jose import JWTError, jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production-use-random-64-char-hex")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30


def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> int:
    """Returns user_id or raises JWTError."""
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    sub = payload.get("sub")
    if sub is None:
        raise JWTError("Invalid token payload")
    return int(sub)


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def verify_metamask(address: str, message: str, signature: str) -> bool:
    """
    Verify a MetaMask personal_sign signature.
    The message must contain a Unix timestamp within 5 minutes of now.
    """
    import logging
    _log = logging.getLogger(__name__)
    try:
        from web3 import Web3
        from eth_account.messages import encode_defunct

        # Extract timestamp from message: "Sign in to Agent Platform\n\nTimestamp: {unix_ts}"
        ts_line = [line for line in message.split("\n") if line.startswith("Timestamp:")]
        if not ts_line:
            _log.warning("verify_metamask: no Timestamp line in message: %r", message)
            return False
        ts = int(ts_line[0].split(":")[1].strip())
        if abs(time.time() - ts) > 300:
            _log.warning("verify_metamask: timestamp expired (diff=%.0fs)", abs(time.time() - ts))
            return False

        w3 = Web3()
        msg = encode_defunct(text=message)
        recovered = w3.eth.account.recover_message(msg, signature=signature)
        _log.info("verify_metamask: recovered=%s expected=%s", recovered.lower(), address.lower())
        return recovered.lower() == address.lower()
    except Exception as e:
        _log.warning("verify_metamask exception: %s", e)
        return False


def verify_phantom(public_key: str, message: str, signature: str) -> bool:
    """
    Verify a Phantom ed25519 signMessage signature.

    Expected message format includes a Unix timestamp line:
      "Timestamp: <unix_ts>"
    Timestamp must be within 5 minutes.
    """
    import logging

    _log = logging.getLogger(__name__)

    try:
        ts_line = [line for line in message.split("\n") if line.startswith("Timestamp:")]
        if not ts_line:
            _log.warning("verify_phantom: no Timestamp line in message")
            return False
        ts = int(ts_line[0].split(":", 1)[1].strip())
        if abs(time.time() - ts) > 300:
            _log.warning("verify_phantom: timestamp expired (diff=%.0fs)", abs(time.time() - ts))
            return False
    except Exception as exc:
        _log.warning("verify_phantom: timestamp parse failed: %s", exc)
        return False

    try:
        from base58 import b58decode
        from nacl.signing import VerifyKey

        pubkey_bytes = b58decode(public_key)
        if len(pubkey_bytes) != 32:
            _log.warning("verify_phantom: invalid pubkey length %d", len(pubkey_bytes))
            return False

        sig_raw = signature.strip()
        sig_bytes: bytes
        try:
            sig_bytes = base64.b64decode(sig_raw, validate=True)
        except Exception:
            if sig_raw.startswith("0x"):
                sig_bytes = bytes.fromhex(sig_raw[2:])
            else:
                sig_bytes = b58decode(sig_raw)

        verify_key = VerifyKey(pubkey_bytes)
        verify_key.verify(message.encode("utf-8"), sig_bytes)
        return True
    except Exception as exc:
        _log.warning("verify_phantom exception: %s", exc)
        return False
