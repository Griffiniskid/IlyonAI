"""Pin tests for spec §1 invariant 5 — session-key on-chain mirror."""
from __future__ import annotations
from decimal import Decimal

import pytest

from src.aa.session_key_mirror import (
    SessionKeyPolicy,
    MirrorVerdict,
    assert_onchain_mirrors,
    build_mirror_drift_blocker,
    compare_policies,
    fetch_onchain_policy,
)
from src.defi.execution.models import KNOWN_BLOCKER_CODES


KEY = "0xAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAaAa"
ACCOUNT = "0xBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBbBb"
CONTRACT_A = "0x1111111111111111111111111111111111111111"
CONTRACT_B = "0x2222222222222222222222222222222222222222"
SEL_TRANSFER = "0xa9059cbb"  # transfer(address,uint256)
SEL_APPROVE = "0x095ea7b3"   # approve(address,uint256)


def _expected() -> SessionKeyPolicy:
    return SessionKeyPolicy(
        key_address=KEY,
        daily_limit_usd=Decimal("1000"),
        expires_at=1_800_000_000,
        allowed_contracts=(CONTRACT_A,),
        allowed_selectors=(SEL_TRANSFER,),
    )


# 1. Blocker code registered

def test_blocker_code_in_known_set():
    assert "SESSION_KEY_MIRROR_DRIFT" in KNOWN_BLOCKER_CODES


# 2. Exact match → matches=True, no drift

def test_compare_match_exact():
    exp = _expected()
    on = SessionKeyPolicy(
        key_address=KEY,
        daily_limit_usd=Decimal("1000"),
        expires_at=1_800_000_000,
        allowed_contracts=(CONTRACT_A,),
        allowed_selectors=(SEL_TRANSFER,),
    )
    v = compare_policies(exp, on)
    assert v.matches is True
    assert v.drift_fields == ()
    assert v.onchain_policy is on
    assert "match" in v.reason.lower()


# 3. Case-insensitive match for hex addresses / selectors

def test_compare_match_case_insensitive_hex():
    exp = _expected()
    on = SessionKeyPolicy(
        key_address=KEY.lower(),
        daily_limit_usd=Decimal("1000"),
        expires_at=1_800_000_000,
        allowed_contracts=(CONTRACT_A.upper().replace("X", "x"),),
        allowed_selectors=(SEL_TRANSFER.upper().replace("X", "x"),),
    )
    v = compare_policies(exp, on)
    assert v.matches is True, v.reason


# 4. key_address drift

def test_drift_key_address():
    exp = _expected()
    on = SessionKeyPolicy(
        key_address="0xcccccccccccccccccccccccccccccccccccccccc",
        daily_limit_usd=Decimal("1000"),
        expires_at=1_800_000_000,
        allowed_contracts=(CONTRACT_A,),
        allowed_selectors=(SEL_TRANSFER,),
    )
    v = compare_policies(exp, on)
    assert v.matches is False
    assert "key_address" in v.drift_fields
    blk = build_mirror_drift_blocker(v)
    assert blk["code"] == "SESSION_KEY_MIRROR_DRIFT"
    assert blk["severity"] == "blocker"
    assert "key_address" in blk["drift_fields"]


# 5. daily_limit_usd drift

def test_drift_daily_limit():
    exp = _expected()
    on = SessionKeyPolicy(
        key_address=KEY,
        daily_limit_usd=Decimal("500"),  # half of expected
        expires_at=1_800_000_000,
        allowed_contracts=(CONTRACT_A,),
        allowed_selectors=(SEL_TRANSFER,),
    )
    v = compare_policies(exp, on)
    assert v.matches is False
    assert v.drift_fields == ("daily_limit_usd",)
    blk = build_mirror_drift_blocker(v)
    assert blk["drift_fields"] == ["daily_limit_usd"]


# 6. expires_at drift

def test_drift_expires_at():
    exp = _expected()
    on = SessionKeyPolicy(
        key_address=KEY,
        daily_limit_usd=Decimal("1000"),
        expires_at=1_700_000_000,  # earlier
        allowed_contracts=(CONTRACT_A,),
        allowed_selectors=(SEL_TRANSFER,),
    )
    v = compare_policies(exp, on)
    assert v.matches is False
    assert "expires_at" in v.drift_fields


# 7. allowed_contracts drift

def test_drift_allowed_contracts():
    exp = _expected()
    on = SessionKeyPolicy(
        key_address=KEY,
        daily_limit_usd=Decimal("1000"),
        expires_at=1_800_000_000,
        allowed_contracts=(CONTRACT_A, CONTRACT_B),  # extra contract added
        allowed_selectors=(SEL_TRANSFER,),
    )
    v = compare_policies(exp, on)
    assert v.matches is False
    assert "allowed_contracts" in v.drift_fields


# 8. allowed_selectors drift

def test_drift_allowed_selectors():
    exp = _expected()
    on = SessionKeyPolicy(
        key_address=KEY,
        daily_limit_usd=Decimal("1000"),
        expires_at=1_800_000_000,
        allowed_contracts=(CONTRACT_A,),
        allowed_selectors=(SEL_TRANSFER, SEL_APPROVE),  # added approve
    )
    v = compare_policies(exp, on)
    assert v.matches is False
    assert "allowed_selectors" in v.drift_fields


# 9. Stub-mode (onchain=None) → onchain_unavailable

def test_stub_mode_onchain_none():
    exp = _expected()
    v = compare_policies(exp, None)
    assert v.matches is False
    assert v.drift_fields == ("onchain_unavailable",)
    assert v.onchain_policy is None
    assert "stub" in v.reason.lower() or "unavailable" in v.reason.lower() or "not available" in v.reason.lower()
    blk = build_mirror_drift_blocker(v)
    assert blk["code"] == "SESSION_KEY_MIRROR_DRIFT"
    assert "onchain_unavailable" in blk["drift_fields"]


# 10. build_mirror_drift_blocker shape

def test_blocker_shape():
    v = MirrorVerdict(
        matches=False,
        drift_fields=("daily_limit_usd", "expires_at"),
        reason="Drift in: daily_limit_usd, expires_at.",
        onchain_policy=None,
    )
    blk = build_mirror_drift_blocker(v)
    assert set(blk.keys()) == {
        "code",
        "severity",
        "title",
        "detail",
        "drift_fields",
        "affected_step_ids",
        "recommended_action",
    }
    assert blk["code"] == "SESSION_KEY_MIRROR_DRIFT"
    assert blk["severity"] == "blocker"
    assert blk["affected_step_ids"] == []
    assert isinstance(blk["drift_fields"], list)
    assert blk["drift_fields"] == ["daily_limit_usd", "expires_at"]
    assert "re-install" in blk["recommended_action"].lower() or "re-install" in blk["recommended_action"]


# 11. Multiple-field drift accumulated in stable order

def test_multi_field_drift_stable_order():
    exp = _expected()
    on = SessionKeyPolicy(
        key_address="0xdddddddddddddddddddddddddddddddddddddddd",
        daily_limit_usd=Decimal("0"),
        expires_at=1,
        allowed_contracts=(CONTRACT_B,),
        allowed_selectors=(SEL_APPROVE,),
    )
    v = compare_policies(exp, on)
    assert v.matches is False
    assert v.drift_fields == (
        "key_address",
        "daily_limit_usd",
        "expires_at",
        "allowed_contracts",
        "allowed_selectors",
    )


# 12. assert_onchain_mirrors end-to-end stub path

@pytest.mark.asyncio
async def test_assert_onchain_mirrors_stub_returns_unavailable():
    exp = _expected()
    v = await assert_onchain_mirrors(
        account_address=ACCOUNT,
        expected=exp,
        chain_id=8453,  # base
        aa_kind="biconomy_nexus",
        rpc_client=object(),  # not used in stub
    )
    assert isinstance(v, MirrorVerdict)
    assert v.matches is False
    assert v.drift_fields == ("onchain_unavailable",)


# 13. fetch_onchain_policy is stub-by-design

@pytest.mark.asyncio
async def test_fetch_onchain_policy_stub_returns_none():
    out = await fetch_onchain_policy(
        ACCOUNT, KEY, 8453, "zerodev_kernel", object()
    )
    assert out is None
