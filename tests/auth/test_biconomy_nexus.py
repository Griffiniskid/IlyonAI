"""Biconomy Nexus wrapper — chain validation + digest equivalence."""
from __future__ import annotations

import pytest

from src.auth.biconomy_nexus import (
    BICONOMY_NEXUS_IMPL,
    NEXUS_CHAIN_IDS,
    NexusAuthRequest,
    assemble_nexus_authorization,
    prepare_nexus_authorization,
    supported_chain,
)
from src.auth.smart_account import authorization_digest


def test_impl_address_pinned():
    assert BICONOMY_NEXUS_IMPL == "0x000000aC74357BFEa72BBD0781833631F732cf19"


def test_supported_chain_ethereum():
    assert supported_chain(1) is True


def test_supported_chain_each_phase6_evm():
    """Every Phase 6 EVM chain expanded in R7 must be supported."""
    for cid in (1, 10, 56, 137, 8453, 42161, 43114, 80094, 59144,
                81457, 5000, 100, 324, 534352, 42220, 130, 146):
        assert supported_chain(cid), f"chain {cid} missing from Nexus support"


def test_unsupported_chain_returns_false():
    assert supported_chain(999_999) is False


def test_prepare_returns_canonical_shape():
    out = prepare_nexus_authorization(
        user_wallet="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        chain_id=1, nonce=0,
    )
    assert set(out.keys()) == {"impl", "chain_id", "nonce", "digest", "wallet"}
    assert out["impl"] == BICONOMY_NEXUS_IMPL
    assert out["digest"].startswith("0x")
    assert len(out["digest"]) == 66  # 0x + 32 bytes hex


def test_prepare_digest_matches_underlying_helper():
    """Sanity check: wrapper digest equals direct helper output."""
    direct = authorization_digest(
        chain_id=1, implementation=BICONOMY_NEXUS_IMPL, nonce=7,
    )
    out = prepare_nexus_authorization(
        user_wallet="0xaaaa", chain_id=1, nonce=7,
    )
    assert out["digest"] == "0x" + direct.hex()


def test_prepare_rejects_unsupported_chain():
    with pytest.raises(ValueError, match="not deployed"):
        prepare_nexus_authorization(
            user_wallet="0xaaaa", chain_id=999_999, nonce=0,
        )


def test_nonce_zero_produces_distinct_digest_from_nonce_one():
    a = prepare_nexus_authorization(user_wallet="0xa", chain_id=1, nonce=0)
    b = prepare_nexus_authorization(user_wallet="0xa", chain_id=1, nonce=1)
    assert a["digest"] != b["digest"]


def test_request_dataclass_implementation_property():
    req = NexusAuthRequest(
        user_wallet="0xaaaa", chain_id=1, nonce=42,
    )
    assert req.implementation == BICONOMY_NEXUS_IMPL


def test_assemble_rejects_unsupported_chain():
    with pytest.raises(ValueError, match="not deployed"):
        assemble_nexus_authorization(
            chain_id=999_999, nonce=0,
            signature_hex="0x" + "00" * 65,
        )


def test_nexus_chain_set_size_at_least_phase6():
    """R7 expansion shipped 18 EVM chains; Nexus should cover them."""
    assert len(NEXUS_CHAIN_IDS) >= 17  # Avalanche + Phase 6 set
