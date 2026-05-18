"""V7-058 pin tests — ed25519 keypair + Phantom XOR roundtrip."""
from __future__ import annotations

import pytest

from src.auth.solana_session import (
    SolanaSessionKeypair,
    decrypt_with_wallet_sig,
    encrypt_with_wallet_sig,
    generate_session_keypair,
)


def test_generate_session_keypair_byte_lengths() -> None:
    kp = generate_session_keypair()
    assert isinstance(kp, SolanaSessionKeypair)
    assert len(kp.private_key) == 32
    assert len(kp.public_key) == 32
    # web3.js-compatible secretKey is 64 bytes (seed || pubkey)
    assert len(kp.secret_key) == 64


def test_generate_session_keypair_is_random() -> None:
    a = generate_session_keypair()
    b = generate_session_keypair()
    assert a.private_key != b.private_key
    assert a.public_key != b.public_key


def test_encrypt_decrypt_roundtrip_recovers_keypair() -> None:
    kp = generate_session_keypair()
    wallet_sig = b"phantom-wallet-signature-bytes-0123456789abcdef" * 2  # 94 bytes
    ct = encrypt_with_wallet_sig(kp, wallet_sig)
    assert isinstance(ct, bytes)
    assert len(ct) == 64
    assert ct != kp.secret_key  # not the plaintext

    recovered = decrypt_with_wallet_sig(ct, wallet_sig)
    assert recovered.private_key == kp.private_key
    assert recovered.public_key == kp.public_key


def test_different_wallet_sig_produces_different_ciphertext() -> None:
    kp = generate_session_keypair()
    sig_a = b"\x01" * 64
    sig_b = b"\x02" * 64
    ct_a = encrypt_with_wallet_sig(kp, sig_a)
    ct_b = encrypt_with_wallet_sig(kp, sig_b)
    assert ct_a != ct_b


def test_decrypt_with_wrong_wallet_sig_yields_garbage() -> None:
    kp = generate_session_keypair()
    sig_real = b"real-wallet-sig" * 4
    sig_wrong = b"wrong-wallet-sig" * 4
    ct = encrypt_with_wallet_sig(kp, sig_real)

    wrong = decrypt_with_wallet_sig(ct, sig_wrong)
    # Structurally valid (32+32) but NOT the original keypair.
    assert len(wrong.private_key) == 32
    assert len(wrong.public_key) == 32
    assert wrong.private_key != kp.private_key
    assert wrong.public_key != kp.public_key


def test_empty_wallet_sig_rejected() -> None:
    kp = generate_session_keypair()
    with pytest.raises(ValueError):
        encrypt_with_wallet_sig(kp, b"")
    with pytest.raises(ValueError):
        decrypt_with_wallet_sig(b"\x00" * 64, b"")


def test_invalid_ciphertext_length_rejected() -> None:
    with pytest.raises(ValueError):
        decrypt_with_wallet_sig(b"\x00" * 32, b"sig")


def test_invalid_keypair_byte_length_rejected() -> None:
    with pytest.raises(ValueError):
        SolanaSessionKeypair(private_key=b"\x00" * 16, public_key=b"\x00" * 32)
    with pytest.raises(ValueError):
        SolanaSessionKeypair(private_key=b"\x00" * 32, public_key=b"\x00" * 16)
