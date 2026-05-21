"""Pin test for Phase C P1-C-005 — D.5 session-key per-action cap.

Spec §11 D.5 mandates a per-action ceiling on session-key authorisations
so a compromised key can't drain everything in one giant transaction
within its 24h allowance window.

Pre-fix: SessionKeyPolicy only had spend_cap_24h_usd + spend_cap_total_usd.
A single $X+1 tx where the period cap was $X would be allowed if the
period had room — no per-action ceiling.

Post-fix: spend_cap_single_tx_usd added; can_authorise checks it FIRST
(before period caps) so a compromised key can't sneak one big drain.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.auth.session_keys import SessionKeyPolicy


def make_policy(**kwargs):
    return SessionKeyPolicy.new(
        user_wallet="0xAAAA",
        chain_id=1,
        scope="aave-v3 supply",
        allowed_protocols=["aave-v3"],
        allowed_actions=["supply"],
        allowed_assets=["USDC"],
        **kwargs,
    )


def test_no_single_tx_cap_allows_any_amount_within_period_cap():
    """Backwards-compat: without spend_cap_single_tx_usd, behaviour matches
    the pre-fix path (only period caps enforced)."""
    p = make_policy(spend_cap_24h_usd=Decimal("1000"))
    ok, reason = p.can_authorise(
        protocol="aave-v3", action="supply", asset="USDC", amount_usd=999,
    )
    assert ok, reason


def test_single_tx_cap_blocks_amount_above_ceiling():
    """The new per-action ceiling refuses any single tx exceeding it,
    regardless of period-cap headroom."""
    p = make_policy(spend_cap_24h_usd=Decimal("10000"), spend_cap_single_tx_usd=Decimal("500"))
    ok, reason = p.can_authorise(
        protocol="aave-v3", action="supply", asset="USDC", amount_usd=501,
    )
    assert not ok
    assert "per-action" in reason.lower()


def test_single_tx_cap_allows_amount_at_or_below_ceiling():
    p = make_policy(spend_cap_24h_usd=Decimal("10000"), spend_cap_single_tx_usd=Decimal("500"))
    ok, reason = p.can_authorise(
        protocol="aave-v3", action="supply", asset="USDC", amount_usd=500,
    )
    assert ok, reason


def test_single_tx_cap_fires_before_period_cap():
    """If both single-tx and 24h caps would block the same tx, the
    refusal MUST cite the per-action cap (it fires first)."""
    p = make_policy(spend_cap_24h_usd=Decimal("100"), spend_cap_single_tx_usd=Decimal("50"))
    ok, reason = p.can_authorise(
        protocol="aave-v3", action="supply", asset="USDC", amount_usd=200,
    )
    assert not ok
    assert "per-action" in reason.lower(), reason


def test_to_row_includes_single_tx_cap():
    p = make_policy(spend_cap_24h_usd=Decimal("1000"), spend_cap_single_tx_usd=Decimal("100"))
    row = p.to_row()
    assert row["spend_cap_single_tx_usd"] == "100"


def test_to_row_omits_single_tx_cap_when_unset():
    p = make_policy(spend_cap_24h_usd=Decimal("1000"))
    row = p.to_row()
    assert row["spend_cap_single_tx_usd"] is None
