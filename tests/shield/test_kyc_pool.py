"""Pin tests for V7-033 / spec §13 row 10 — PERMISSIONED_POOL_KYC.

Covers the registry lookup primitives and the preflight wire that
emits one ExecutionBlocker per gated pool address. The registry
must be case-insensitive (EIP-55 mixed-case inputs); the preflight
wire must dedupe per-address so two steps referencing the same
gated pool surface a single blocker; unknown pools must never
synthesise a false-positive blocker.
"""
from __future__ import annotations

import pytest

from src.shield.kyc_pool import (
    KYC_GATED_POOLS,
    PERMISSIONED_POOL_KYC_BLOCKER_CODE,
    check_kyc_pool,
    evaluate_kyc_pool_preflight,
    is_kyc_gated,
)

# Pull a canonical registered address out of the static registry rather
# than hard-coding one — keeps the test honest against future churn.
REGISTERED_ADDR = next(iter(KYC_GATED_POOLS))
RANDOM_ADDR = "0xDeadBeef00000000000000000000000000000000"


def test_is_kyc_gated_returns_true_for_registered_addr_case_insensitive() -> None:
    # exact lowercase match
    assert is_kyc_gated(REGISTERED_ADDR) is True
    # EIP-55 mixed-case must still match
    assert is_kyc_gated(REGISTERED_ADDR.upper()) is True
    mixed = "0x" + REGISTERED_ADDR[2:4].upper() + REGISTERED_ADDR[4:]
    assert is_kyc_gated(mixed) is True


def test_is_kyc_gated_returns_false_for_random_addr() -> None:
    assert is_kyc_gated(RANDOM_ADDR) is False
    assert is_kyc_gated("") is False
    assert is_kyc_gated(None) is False  # type: ignore[arg-type]


def test_check_kyc_pool_returns_code_for_gated_else_none() -> None:
    assert check_kyc_pool(REGISTERED_ADDR) == PERMISSIONED_POOL_KYC_BLOCKER_CODE
    assert check_kyc_pool(REGISTERED_ADDR.upper()) == PERMISSIONED_POOL_KYC_BLOCKER_CODE
    assert check_kyc_pool(RANDOM_ADDR) is None
    assert check_kyc_pool("") is None


def test_evaluate_kyc_pool_preflight_returns_blockers_list() -> None:
    # empty input → empty output, never raises
    assert evaluate_kyc_pool_preflight([]) == []
    assert evaluate_kyc_pool_preflight([RANDOM_ADDR]) == []

    blockers = evaluate_kyc_pool_preflight([REGISTERED_ADDR])
    assert len(blockers) == 1
    b = blockers[0]
    assert b.code == PERMISSIONED_POOL_KYC_BLOCKER_CODE
    assert b.severity == "blocker"
    assert b.recoverable is False
    assert REGISTERED_ADDR in b.detail


def test_evaluate_kyc_pool_preflight_dedupes_case_insensitively() -> None:
    # same gated addr referenced twice (one mixed-case) → single blocker
    blockers = evaluate_kyc_pool_preflight(
        [REGISTERED_ADDR, REGISTERED_ADDR.upper(), RANDOM_ADDR]
    )
    assert len(blockers) == 1
    assert blockers[0].code == PERMISSIONED_POOL_KYC_BLOCKER_CODE


def test_evaluate_kyc_pool_preflight_propagates_affected_step_ids() -> None:
    blockers = evaluate_kyc_pool_preflight(
        [REGISTERED_ADDR], affected_step_ids=["step_001", "step_002"]
    )
    assert len(blockers) == 1
    assert blockers[0].affected_step_ids == ["step_001", "step_002"]


# ---------------------------------------------------------------------------
# V7-033 — Registry must contain real, on-chain-verified gated pool addresses.
# Each address quoted below was independently verified on Etherscan against
# the protocol's published canonical deployment list (see src/shield/kyc_pool.py
# for full source-URL citations). These pins guard against silent registry
# regressions ("oh the placeholder is gone, who needs the real ones").
# ---------------------------------------------------------------------------


def test_registry_contains_maple_syrup_usdc_pool() -> None:
    """Maple Syrup USDC pool (PoolV2 token). Verified via
    https://etherscan.io/address/0x80ac24aA929eaF5013f6436cdA2a7ba190f5Cc0b
    (Etherscan name "MaplePool", symbol "syrupUSDC")."""
    assert is_kyc_gated("0x80ac24aA929eaF5013f6436cdA2a7ba190f5Cc0b") is True
    assert is_kyc_gated("0x80ac24aa929eaf5013f6436cda2a7ba190f5cc0b") is True


def test_registry_contains_maple_syrup_usdt_pool() -> None:
    """Maple Syrup USDT pool (PoolV2 token). Verified via
    https://etherscan.io/address/0x356B8d89c1e1239Cbbb9dE4815c39A1474d5BA7D
    (Etherscan name "MaplePool", symbol "syrupUSDT")."""
    assert is_kyc_gated("0x356B8d89c1e1239Cbbb9dE4815c39A1474d5BA7D") is True


def test_registry_contains_goldfinch_senior_pool() -> None:
    """Goldfinch Senior Pool (EIP-173 proxy). Requires UID NFT (KYC).
    Verified via
    https://etherscan.io/address/0x8481a6EbAf5c7DABc3F7e09e44A89531fd31F822
    (Etherscan name "Goldfinch Protocol: Senior Pool")."""
    assert is_kyc_gated("0x8481a6EbAf5c7DABc3F7e09e44A89531fd31F822") is True


def test_registry_contains_hashnote_usyc() -> None:
    """Hashnote USYC (US Yield Coin) tokenised T-bill fund. Mint/burn
    requires off-platform KYC + accredited-investor onboarding. Verified
    via https://etherscan.io/token/0x136471a34f6ef19fE571EFFC1CA711fdb8E49f2b
    (Etherscan name "US Yield Coin", symbol "USYC")."""
    assert is_kyc_gated("0x136471a34f6ef19fE571EFFC1CA711fdb8E49f2b") is True


def test_registry_has_at_least_three_real_addresses() -> None:
    """Guard against the registry collapsing back to a single placeholder.
    Spec §13 row 10 names five gated protocols (Aave Arc, Maple,
    Goldfinch, Hashnote, Compound III KYC variants) — we require at least
    three live entries before this test passes."""
    assert len(KYC_GATED_POOLS) >= 3


# ---------------------------------------------------------------------------
# V7-033 — preflight wire-up. Spec §13 row 10 says the blocker must be
# emitted from evaluate_preflight() (the canonical entry point), not just
# the standalone evaluate_kyc_pool_preflight() helper. This pin asserts
# the call chain so a future refactor that drops the wire surfaces here.
# ---------------------------------------------------------------------------


def test_evaluate_preflight_emits_kyc_blocker_for_gated_supply_step() -> None:
    """A supply step whose transaction lands on a KYC-gated pool address
    must surface a PERMISSIONED_POOL_KYC blocker from evaluate_preflight."""
    from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction
    from src.defi.execution.preflight import WalletInventory, evaluate_preflight

    # Maple syrupUSDC pool — gated by MaplePoolPermissionManager.
    gated_pool = "0x80ac24aA929eaF5013f6436cdA2a7ba190f5Cc0b"
    step = ExecutionStepV3(
        step_id="step_kyc_001",
        index=1,
        action="supply",
        title="Supply USDC into Maple Syrup",
        description="Deposit USDC into permissioned Maple lending pool.",
        chain="ethereum",
        wallet="MetaMask",
        protocol="maple",
        asset_in="USDC",
        amount_in="0",  # zero amount keeps balance check inert; we're
                       # only exercising the KYC gate here.
        transaction=UnsignedStepTransaction(
            chain_kind="evm",
            chain_id=1,
            to=gated_pool,
        ),
    )
    inv = WalletInventory(
        evm_address="0x000000000000000000000000000000000000dEaD",
        chain_id=1,
    )
    blockers = evaluate_preflight(
        steps=[step],
        inventory=inv,
        min_native_gas={"ethereum": 0.0},  # disable gas check
    )
    codes = [b.code for b in blockers]
    assert PERMISSIONED_POOL_KYC_BLOCKER_CODE in codes, (
        f"expected PERMISSIONED_POOL_KYC blocker, got codes={codes!r}"
    )
    kyc_blocker = next(b for b in blockers if b.code == PERMISSIONED_POOL_KYC_BLOCKER_CODE)
    assert kyc_blocker.severity == "blocker"
    assert kyc_blocker.recoverable is False
    assert "step_kyc_001" in kyc_blocker.affected_step_ids


def test_evaluate_preflight_no_kyc_blocker_for_open_pool() -> None:
    """A supply step whose target is NOT in the gated registry must not
    synthesise a false-positive PERMISSIONED_POOL_KYC blocker."""
    from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction
    from src.defi.execution.preflight import WalletInventory, evaluate_preflight

    open_pool = "0xDeadBeef00000000000000000000000000000000"
    step = ExecutionStepV3(
        step_id="step_open_001",
        index=1,
        action="supply",
        title="Supply USDC into Aave V3",
        description="Open lending market — no whitelist.",
        chain="ethereum",
        wallet="MetaMask",
        protocol="aave-v3",
        asset_in="USDC",
        amount_in="0",
        transaction=UnsignedStepTransaction(
            chain_kind="evm",
            chain_id=1,
            to=open_pool,
        ),
    )
    inv = WalletInventory(
        evm_address="0x000000000000000000000000000000000000dEaD",
        chain_id=1,
    )
    blockers = evaluate_preflight(
        steps=[step],
        inventory=inv,
        min_native_gas={"ethereum": 0.0},
    )
    codes = [b.code for b in blockers]
    assert PERMISSIONED_POOL_KYC_BLOCKER_CODE not in codes
