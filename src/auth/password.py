"""Password hashing utilities using argon2."""
from __future__ import annotations

from passlib.hash import argon2


def hash_password(pw: str) -> str:
    """Return an argon2 hash of *pw*."""
    return argon2.hash(pw)


def verify_password(pw: str, digest: str) -> bool:
    """Return True when *pw* matches the argon2 *digest*."""
    return argon2.verify(pw, digest)
