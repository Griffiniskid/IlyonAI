"""Tests for src/auth/smart_account.py — EIP-7702 helpers."""
from __future__ import annotations

import pytest

from src.auth.smart_account import (
    BICONOMY_NEXUS_IMPL,
    MAGIC_BYTE,
    Eip7702Authorization,
    _rlp_encode_authorization,
    authorization_digest,
    build_authorization_from_signature,
)


def test_magic_byte_is_0x05():
    assert MAGIC_BYTE == b"\x05"


def test_biconomy_impl_is_20_bytes():
    addr_bytes = bytes.fromhex(BICONOMY_NEXUS_IMPL.removeprefix("0x"))
    assert len(addr_bytes) == 20


def test_rlp_encodes_canonical_tuple():
    enc = _rlp_encode_authorization(
        chain_id=1, implementation=BICONOMY_NEXUS_IMPL, nonce=0,
    )
    # RLP list with three items: starts with 0xc0 + payload length.
    assert enc[0] >= 0xc0


def test_rlp_rejects_short_address():
    with pytest.raises(ValueError, match="20 bytes"):
        _rlp_encode_authorization(chain_id=1, implementation="0xabcd", nonce=0)


def test_authorization_digest_is_32_bytes():
    d = authorization_digest(chain_id=1, implementation=BICONOMY_NEXUS_IMPL, nonce=42)
    assert isinstance(d, bytes) and len(d) == 32


def test_build_authorization_round_trip():
    sig_hex = "0x" + "a" * 64 + "b" * 64 + "1b"  # r=aa..., s=bb..., v=27
    auth = build_authorization_from_signature(
        chain_id=1, implementation=BICONOMY_NEXUS_IMPL, nonce=7,
        signature_hex=sig_hex,
    )
    assert isinstance(auth, Eip7702Authorization)
    assert auth.chain_id == 1
    assert auth.nonce == 7
    assert auth.y_parity == 0  # 27 - 27
    assert len(auth.r) == 32 and len(auth.s) == 32
    t = auth.to_tuple()
    assert len(t) == 6


def test_signature_v_28_maps_to_y_parity_1():
    sig_hex = "0x" + "0" * 128 + "1c"  # v=28
    auth = build_authorization_from_signature(
        chain_id=1, implementation=BICONOMY_NEXUS_IMPL, nonce=0,
        signature_hex=sig_hex,
    )
    assert auth.y_parity == 1


def test_signature_invalid_length_raises():
    with pytest.raises(ValueError, match="65 bytes"):
        build_authorization_from_signature(
            chain_id=1, implementation=BICONOMY_NEXUS_IMPL, nonce=0,
            signature_hex="0xabcd",
        )
