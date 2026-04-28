"""Unit tests for src.allocator.composer."""
from __future__ import annotations

import pytest

from src.allocator.composer import (
    PoolCandidate,
    compose_allocation,
    execution_steps_from_positions,
    summarise_positions,
    total_gas_from_steps,
    wallets_summary_from_steps,
    weighted_sentinel,
    rank_candidates,
)


def _demo_universe() -> list[PoolCandidate]:
    """Five golden pools that mirror the demo exactly + noise."""
    return [
        # The five demo picks:
        PoolCandidate(project="Lido", symbol="STETH", chain="Ethereum",
                      tvl_usd=24_500_000_000, apy=3.1, audits=True, days_live=1800,
                      stable=False, il_risk="no", exposure="single"),
        PoolCandidate(project="Rocket Pool", symbol="RETH", chain="Ethereum",
                      tvl_usd=3_400_000_000, apy=2.9, audits=True, days_live=1500,
                      stable=False, il_risk="no", exposure="single",
                      raw_flags=("Node operator set",)),
        PoolCandidate(project="Jito", symbol="JITOSOL", chain="Solana",
                      tvl_usd=2_100_000_000, apy=7.2, audits=True, days_live=800,
                      stable=False, il_risk="no", exposure="single",
                      raw_flags=("MEV rebate dependency",)),
        PoolCandidate(project="Aave v3", symbol="AARBUSDC", chain="Arbitrum",
                      tvl_usd=890_000_000, apy=4.8, audits=True, days_live=700,
                      stable=True, il_risk="no", exposure="single"),
        PoolCandidate(project="Pendle", symbol="PT-sUSDe", chain="Ethereum",
                      tvl_usd=320_000_000, apy=18.2, audits=True, days_live=400,
                      stable=True, il_risk="no", exposure="single",
                      raw_flags=("Fixed maturity", "Ethena dependency")),
        # Noise that should be dropped:
        PoolCandidate(project="junk", symbol="JUNK", chain="Ethereum",
                      tvl_usd=500_000, apy=612000, audits=False, days_live=30,
                      stable=False, il_risk="yes", exposure="multi"),
        PoolCandidate(project="new-proto", symbol="NEW", chain="BSC",
                      tvl_usd=250_000_000, apy=42, audits=False, days_live=15,
                      stable=False, il_risk="yes", exposure="multi"),
    ]


def test_weighted_sentinel_rounds_to_int():
    assert weighted_sentinel(100, 100, 100, 100) == 100
    assert weighted_sentinel(0, 0, 0, 0) == 0
    # 0.4 * 96 + 0.25 * 92 + 0.2 * 98 + 0.15 * 95 = 38.4 + 23 + 19.6 + 14.25 = 95.25 → 95
    assert weighted_sentinel(96, 92, 98, 95) == 95


def test_rank_drops_junk_and_new_protocols():
    """TVL < 200M, days_live < 180, APY > 500 must be filtered."""
    pools = _demo_universe()
    ranked = rank_candidates(pools, risk_budget="balanced")
    projects = {c.project for (c, *_rest) in ranked}
    assert "junk" not in projects
    assert "new-proto" not in projects
    assert {"Lido", "Rocket Pool", "Jito", "Aave v3", "Pendle"}.issubset(projects)


def test_compose_picks_five_with_balanced_mix():
    pools = _demo_universe()
    positions = compose_allocation(pools, usd_amount=10_000, risk_budget="balanced")
    assert len(positions) == 5
    assert sum(p.weight for p in positions) == 100
    assert all(p.weight <= 35 for p in positions)
    # Ranks are 1..5 contiguous
    assert [p.rank for p in positions] == [1, 2, 3, 4, 5]
    # Must have multiple chains for diversity
    chains = {p.chain for p in positions}
    assert len(chains) >= 2


def test_compose_tags_risk_buckets():
    pools = _demo_universe()
    positions = compose_allocation(pools, usd_amount=10_000, risk_budget="balanced")
    risks = [p.risk for p in positions]
    # Balanced should have at least 3 low-risk
    assert risks.count("low") >= 3


def test_conservative_drops_medium():
    pools = _demo_universe()
    positions = compose_allocation(pools, usd_amount=10_000, risk_budget="conservative")
    for p in positions:
        assert p.sentinel >= 82


def test_summarise_positions_emits_blended_apy_and_mix():
    pools = _demo_universe()
    positions = compose_allocation(pools, usd_amount=10_000, risk_budget="balanced")
    s = summarise_positions(positions, 10_000)
    assert s["total_usd"] == "$10,000"
    assert s["blended_apy"].startswith("~")
    assert s["blended_apy"].endswith("%")
    assert s["chains"] >= 2
    assert 50 <= s["weighted_sentinel"] <= 100
    assert s["risk_mix"]["low"] + s["risk_mix"]["medium"] + s["risk_mix"]["high"] == 5
    assert s["combined_tvl"].startswith("$")


def test_execution_steps_match_positions():
    pools = _demo_universe()
    positions = compose_allocation(pools, usd_amount=10_000, risk_budget="balanced")
    steps = execution_steps_from_positions(positions, 10_000)
    assert len(steps) == len(positions)
    for st, pos in zip(steps, positions):
        assert st["index"] == pos.rank
        assert st["chain"] == pos.chain
        assert st["router"] == pos.router
        assert st["gas"].startswith("~$")
    # Solana should map to Phantom, others MetaMask
    wallets = {st["wallet"] for st in steps}
    assert "MetaMask" in wallets


def test_total_gas_sums_steps():
    steps = [
        {"gas": "~$4.80"}, {"gas": "~$5.10"}, {"gas": "~$0.01"},
        {"gas": "~$0.35"}, {"gas": "~$6.90"},
    ]
    assert total_gas_from_steps(steps) == "~$17.16"


def test_wallets_summary_sorted_unique():
    steps = [{"wallet": "MetaMask"}, {"wallet": "Phantom"}, {"wallet": "MetaMask"}]
    assert wallets_summary_from_steps(steps) == "MetaMask + Phantom"


def test_empty_pool_universe_returns_empty():
    positions = compose_allocation([], usd_amount=10_000, risk_budget="balanced")
    assert positions == []
    s = summarise_positions(positions, 10_000)
    assert s["weighted_sentinel"] == 0
