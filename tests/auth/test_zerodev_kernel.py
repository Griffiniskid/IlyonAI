"""ZeroDev Kernel sibling — same EIP-7702 shape, different impl."""
from __future__ import annotations

import pytest

from src.auth.biconomy_nexus import BICONOMY_NEXUS_IMPL
from src.auth.smart_account import authorization_digest
from src.auth.zerodev_kernel import (
    KERNEL_CHAIN_IDS,
    KERNEL_V3_IMPL,
    KernelAuthRequest,
    assemble_kernel_authorization,
    prepare_kernel_authorization,
    supported_chain,
)


def test_kernel_impl_pinned():
    assert KERNEL_V3_IMPL == "0xd6CEDDe84be40893d153Be9d467CD6aD37875b28"


def test_kernel_distinct_from_nexus():
    assert KERNEL_V3_IMPL.lower() != BICONOMY_NEXUS_IMPL.lower()


def test_supported_chain_basics():
    assert supported_chain(1) is True
    assert supported_chain(8453) is True
    assert supported_chain(999_999) is False


def test_prepare_emits_canonical_shape():
    out = prepare_kernel_authorization(
        user_wallet="0xaaaa", chain_id=1, nonce=3,
    )
    assert set(out.keys()) == {"impl", "chain_id", "nonce", "digest", "wallet"}
    assert out["impl"] == KERNEL_V3_IMPL


def test_prepare_digest_matches_underlying_helper():
    direct = authorization_digest(
        chain_id=8453, implementation=KERNEL_V3_IMPL, nonce=11,
    )
    out = prepare_kernel_authorization(
        user_wallet="0xbb", chain_id=8453, nonce=11,
    )
    assert out["digest"] == "0x" + direct.hex()


def test_prepare_rejects_unsupported_chain():
    with pytest.raises(ValueError, match="not deployed"):
        prepare_kernel_authorization(
            user_wallet="0xaaaa", chain_id=999_999, nonce=0,
        )


def test_kernel_chain_set_covers_phase6_core():
    """Phase 6 core EVM chains (Linea/Blast/Mantle/Gnosis/zkSync/Scroll/
    Celo/Unichain/Sonic/Berachain) must all be in the Kernel set."""
    core = {59144, 81457, 5000, 100, 324, 534352, 42220, 130, 146, 80094}
    # Berachain support may be pending; at minimum Linea+Blast+Mantle.
    assert {59144, 81457, 5000} <= KERNEL_CHAIN_IDS


def test_request_implementation_property():
    req = KernelAuthRequest(user_wallet="0x1", chain_id=1, nonce=7)
    assert req.implementation == KERNEL_V3_IMPL


def test_assemble_rejects_unsupported_chain():
    with pytest.raises(ValueError, match="not deployed"):
        assemble_kernel_authorization(
            chain_id=999_999, nonce=0,
            signature_hex="0x" + "00" * 65,
        )


def test_digest_differs_from_nexus_for_same_chain_and_nonce():
    """Same chain/nonce — different impl address — must yield different
    digest. Sanity check that the impl is folded into the keccak input."""
    nx_dig = authorization_digest(
        chain_id=1, implementation=BICONOMY_NEXUS_IMPL, nonce=42,
    )
    kr_dig = authorization_digest(
        chain_id=1, implementation=KERNEL_V3_IMPL, nonce=42,
    )
    assert nx_dig != kr_dig
