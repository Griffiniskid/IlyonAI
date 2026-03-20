"""Helpers for webhook payload signature validation."""

import hashlib
import hmac


def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify an HMAC SHA-256 webhook signature."""
    if not payload or not signature or not secret:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
