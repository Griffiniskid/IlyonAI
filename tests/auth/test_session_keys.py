"""Tests for src/auth/session_keys.py — off-chain enforcement model."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.auth.session_keys import SessionKeyPolicy, revoke_policy


def _new_policy(**overrides):
    defaults = dict(
        user_wallet="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        chain_id=1,
        scope="aave-v3 supply USDC",
        allowed_protocols=("aave-v3",),
        allowed_actions=("supply", "withdraw"),
        allowed_assets=("USDC",),
        spend_cap_24h_usd=Decimal("1000"),
        spend_cap_total_usd=Decimal("10000"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    defaults.update(overrides)
    return SessionKeyPolicy.new(**defaults)


def test_new_assigns_uuid_and_lowercases_wallet():
    p = _new_policy()
    assert len(p.policy_id) == 36
    assert p.user_wallet == p.user_wallet.lower()


def test_active_by_default():
    p = _new_policy()
    assert p.is_active() is True


def test_revoked_policy_inactive():
    p = _new_policy()
    revoke_policy(p)
    assert p.is_active() is False


def test_expired_policy_inactive():
    p = _new_policy(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
    assert p.is_active() is False


def test_can_authorise_happy_path():
    p = _new_policy()
    ok, reason = p.can_authorise(
        protocol="aave-v3", action="supply", asset="USDC", amount_usd=100,
    )
    assert ok is True
    assert reason == ""


def test_can_authorise_rejects_wrong_protocol():
    p = _new_policy()
    ok, reason = p.can_authorise(
        protocol="compound-v3", action="supply", asset="USDC", amount_usd=100,
    )
    assert ok is False
    assert "protocol" in reason


def test_can_authorise_rejects_wrong_action():
    p = _new_policy()
    ok, reason = p.can_authorise(
        protocol="aave-v3", action="claim", asset="USDC", amount_usd=100,
    )
    assert ok is False
    assert "action" in reason


def test_can_authorise_rejects_wrong_asset():
    p = _new_policy()
    ok, reason = p.can_authorise(
        protocol="aave-v3", action="supply", asset="DAI", amount_usd=100,
    )
    assert ok is False
    assert "asset" in reason


def test_can_authorise_rejects_when_24h_cap_breached():
    p = _new_policy(spend_cap_24h_usd=Decimal("50"))
    p.record_spend(40)
    ok, reason = p.can_authorise(
        protocol="aave-v3", action="supply", asset="USDC", amount_usd=20,
    )
    assert ok is False
    assert "24h spend cap" in reason


def test_can_authorise_rejects_when_total_cap_breached():
    p = _new_policy(spend_cap_total_usd=Decimal("100"))
    p.record_spend(90)
    ok, reason = p.can_authorise(
        protocol="aave-v3", action="supply", asset="USDC", amount_usd=20,
    )
    assert ok is False
    assert "total spend cap" in reason


def test_record_spend_accumulates():
    p = _new_policy()
    p.record_spend(10)
    p.record_spend(15)
    assert p.spent_total_usd == Decimal("25")
    assert p.spent_24h_usd == Decimal("25")


def test_to_row_serialises_lists_as_json():
    p = _new_policy()
    row = p.to_row()
    import json
    assert json.loads(row["allowed_protocols_json"]) == ["aave-v3"]
    assert json.loads(row["allowed_actions_json"]) == ["supply", "withdraw"]
    assert json.loads(row["allowed_assets_json"]) == ["USDC"]
