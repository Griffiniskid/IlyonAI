"""Solana session-key cryptography — V7-058 extraction.

Standalone ed25519 keypair helpers + Phantom-compatible XOR encryption used
to seal ephemeral session keypairs at rest with a key derived from the
user's Phantom wallet signature.

The "Phantom XOR pattern" is the same lightweight envelope Phantom's
sessionStorage encryption uses for ephemeral session signers:

    cipher_key   = SHA-256(wallet_sig)
    ciphertext_i = plaintext_i  XOR  cipher_key[i mod 32]

It is **not** authenticated encryption — it merely prevents casual disk-
scrape recovery of the ephemeral signer's private bytes. The wallet
signature is the only secret; if an attacker captures both `ciphertext`
and `wallet_sig` they recover the keypair, by design (the wallet sig is
re-derived on demand and never persisted).

The functions here are pure (no I/O, no aiohttp coupling) so they can be
unit-tested and reused from the autonomous-rebalance signer path without
dragging in route-layer dependencies.

See also: `src/api/routes/eip7702_auth.py::register_solana_session_signer`
which records the *public* half of the resulting keypair against the
user's wallet (the private half stays encrypted client-side).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from nacl.signing import SigningKey


@dataclass(frozen=True)
class SolanaSessionKeypair:
    """ed25519 keypair holder for a Solana session signer.

    `private_key` is the 32-byte seed (ed25519 secret scalar input).
    `public_key`  is the 32-byte compressed Edwards point.

    These match the byte layout libsodium / @solana/web3.js use for
    `Keypair.fromSecretKey(...)` (where the 64-byte secretKey is the
    concatenation of seed || pubkey).
    """

    private_key: bytes
    public_key: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.private_key, (bytes, bytearray)) or len(self.private_key) != 32:
            raise ValueError("private_key must be 32 bytes")
        if not isinstance(self.public_key, (bytes, bytearray)) or len(self.public_key) != 32:
            raise ValueError("public_key must be 32 bytes")

    @property
    def secret_key(self) -> bytes:
        """64-byte web3.js-compatible secretKey = seed || pubkey."""
        return bytes(self.private_key) + bytes(self.public_key)


def generate_session_keypair() -> SolanaSessionKeypair:
    """Generate a fresh ed25519 keypair using libsodium's CSPRNG."""
    signing_key = SigningKey.generate()
    private_bytes = bytes(signing_key)                     # 32-byte seed
    public_bytes = bytes(signing_key.verify_key)           # 32-byte pubkey
    return SolanaSessionKeypair(private_key=private_bytes, public_key=public_bytes)


def _derive_cipher_key(wallet_sig: bytes) -> bytes:
    if not isinstance(wallet_sig, (bytes, bytearray)) or len(wallet_sig) == 0:
        raise ValueError("wallet_sig must be non-empty bytes")
    return hashlib.sha256(bytes(wallet_sig)).digest()  # 32 bytes


def _xor_stream(data: bytes, key: bytes) -> bytes:
    klen = len(key)
    return bytes(b ^ key[i % klen] for i, b in enumerate(data))


def encrypt_with_wallet_sig(keypair: SolanaSessionKeypair, wallet_sig: bytes) -> bytes:
    """Seal a session keypair with the SHA-256(wallet_sig) XOR cipher.

    Returns the ciphertext for the 64-byte `seed || pubkey` plaintext. The
    pubkey is included so callers can recover the full keypair from the
    ciphertext alone (no separate pubkey storage required).
    """
    cipher_key = _derive_cipher_key(wallet_sig)
    plaintext = keypair.secret_key  # 64 bytes
    return _xor_stream(plaintext, cipher_key)


def decrypt_with_wallet_sig(ciphertext: bytes, wallet_sig: bytes) -> SolanaSessionKeypair:
    """Reverse of `encrypt_with_wallet_sig`.

    Does *not* authenticate — a wrong `wallet_sig` returns a structurally
    valid but garbage `SolanaSessionKeypair`. Callers that need integrity
    must verify the recovered pubkey against an out-of-band reference (e.g.
    the `solana_session_signers.signer_pubkey` row).
    """
    if not isinstance(ciphertext, (bytes, bytearray)) or len(ciphertext) != 64:
        raise ValueError("ciphertext must be 64 bytes (seed || pubkey)")
    cipher_key = _derive_cipher_key(wallet_sig)
    plaintext = _xor_stream(bytes(ciphertext), cipher_key)
    return SolanaSessionKeypair(private_key=plaintext[:32], public_key=plaintext[32:])


__all__ = [
    "SolanaSessionKeypair",
    "generate_session_keypair",
    "encrypt_with_wallet_sig",
    "decrypt_with_wallet_sig",
]
