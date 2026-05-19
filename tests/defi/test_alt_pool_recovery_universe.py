"""RC14 pin tests — Slipstream / alt-pool recovery populates alternatives.

Pre-RC14 behaviour (G04 t4 / F05): the ADAPTER_BUILD_FAILED recovery path in
`build_yield_execution_plan` left `recovery.alternatives` as the default
empty list, so the agent issued a fresh `search_defi_opportunities` call
instead of substituting from the universe it had already ranked.

These pins assert:
  1. The strategy-memory search-universe cache stores + recalls candidates.
  2. `pick_alt_pools` returns ≠ [] when the universe has supportable
     alternatives for the failed (chain, asset, protocol).
  3. The just-failed pool is filtered out by pool_id and by
     same-protocol+same-chain.
  4. Ranking prefers same-chain, same-asset, executable, then APY.
  5. The recovery payload emitted by `build_yield_execution_plan` on an
     adapter-build failure carries non-empty `alternatives` when a search
     universe is cached on the same session.

Run with:
    pytest tests/defi/test_alt_pool_recovery_universe.py -q
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.defi.strategy.memory import (
    clear_all_for_test,
    pick_alt_pools,
    recall_search_universe,
    remember_search_universe,
)


@pytest.fixture(autouse=True)
def _isolate_memory():
    """Each test gets a clean in-process strategy memory."""
    clear_all_for_test()
    yield
    clear_all_for_test()


def _candidate(
    pool_id: str,
    *,
    protocol: str = "aave-v3",
    chain: str = "base",
    symbol: str = "USDC",
    apy: float = 5.0,
    tvl_usd: float = 50_000_000,
    executable: bool = True,
) -> dict[str, Any]:
    return {
        "pool_id": pool_id,
        "protocol": protocol.title(),
        "protocol_slug": protocol,
        "chain": chain,
        "symbol": symbol,
        "apy": apy,
        "tvl_usd": tvl_usd,
        "risk_level": "LOW",
        "executable": executable,
        "adapter_id": "deterministic" if executable else None,
        "source_urls": {},
    }


def test_remember_and_recall_search_universe():
    """The cache round-trips. Capped at 32 entries to bound memory."""
    universe = [_candidate(f"p{i}", apy=10 + i) for i in range(40)]
    remember_search_universe("sess-1", universe)
    cached = recall_search_universe("sess-1")
    assert len(cached) == 32
    assert cached[0]["pool_id"] == "p0"


def test_pick_alt_pools_filters_failed_pool_id():
    """The just-failed pool_id must not appear in alternatives."""
    universe = [
        _candidate("failed-pool", protocol="slipstream", chain="base", apy=8.0),
        _candidate("alt-1", protocol="compound-v3", chain="base", apy=6.0),
        _candidate("alt-2", protocol="aave-v3", chain="base", apy=5.5),
    ]
    remember_search_universe("sess-2", universe)
    alts = pick_alt_pools(
        "sess-2",
        failed_pool_id="failed-pool",
        failed_protocol="slipstream",
        chain="base",
        asset="USDC",
    )
    assert alts, "alternatives must not be empty when universe has supportable pools"
    assert all(a["pool_id"] != "failed-pool" for a in alts)


def test_pick_alt_pools_filters_same_protocol_same_chain():
    """Same protocol on same chain is almost certainly the same pool —
    alt-pool recovery means a different route."""
    universe = [
        _candidate("failed-pool", protocol="aave-v3", chain="base"),
        _candidate("aave-base-dup", protocol="aave-v3", chain="base"),
        _candidate("compound-base", protocol="compound-v3", chain="base", apy=4.5),
        _candidate("aave-arbitrum", protocol="aave-v3", chain="arbitrum", apy=5.5),
    ]
    remember_search_universe("sess-3", universe)
    alts = pick_alt_pools(
        "sess-3",
        failed_pool_id="failed-pool",
        failed_protocol="aave-v3",
        chain="base",
        asset="USDC",
    )
    pids = {a["pool_id"] for a in alts}
    # Same protocol + same chain duplicate is dropped.
    assert "aave-base-dup" not in pids
    # Different protocol on same chain survives.
    assert "compound-base" in pids
    # Same protocol on different chain survives (it's a different route).
    assert "aave-arbitrum" in pids


def test_pick_alt_pools_ranks_same_chain_first():
    """Same-chain alternatives outrank cross-chain ones."""
    universe = [
        _candidate("eth-usdc", chain="ethereum", protocol="compound-v3", apy=4.0),
        _candidate("base-usdc", chain="base", protocol="compound-v3", apy=3.0),
        _candidate("arb-usdc", chain="arbitrum", protocol="compound-v3", apy=5.0),
    ]
    remember_search_universe("sess-4", universe)
    alts = pick_alt_pools(
        "sess-4",
        failed_pool_id="some-failed-pool",
        failed_protocol="aave-v3",
        chain="base",
        asset="USDC",
        limit=3,
    )
    assert alts[0]["pool_id"] == "base-usdc", (
        "same-chain alternative must rank first, got: "
        + ", ".join(a["pool_id"] for a in alts)
    )


def test_pick_alt_pools_ranks_executable_before_link_only():
    """Within same chain + asset, executable candidates outrank link_only."""
    universe = [
        _candidate("link-only-pool", chain="base", protocol="curve",
                   apy=10.0, executable=False),
        _candidate("executable-pool", chain="base", protocol="compound-v3",
                   apy=8.0, executable=True),
    ]
    remember_search_universe("sess-5", universe)
    alts = pick_alt_pools(
        "sess-5",
        failed_pool_id="failed",
        failed_protocol="aave-v3",
        chain="base",
        asset="USDC",
    )
    assert alts[0]["pool_id"] == "executable-pool"


def test_pick_alt_pools_no_universe_returns_empty():
    """No universe cached for the session → safely returns []."""
    alts = pick_alt_pools(
        "no-session",
        failed_pool_id="x",
        failed_protocol="aave-v3",
        chain="base",
        asset="USDC",
    )
    assert alts == []


# ── End-to-end: build_yield_execution_plan emits non-empty alternatives ─────


@pytest.mark.asyncio
async def test_build_yield_exec_plan_recovery_populates_alternatives(monkeypatch):
    """RC14 end-to-end: ADAPTER_BUILD_FAILED path must surface alternatives
    from the cached search universe instead of an empty list."""
    import importlib

    from src.agent.tools._base import ToolCtx
    from src.api.schemas.agent import ToolEnvelope

    byep_mod = importlib.import_module(
        "src.agent.tools.build_yield_execution_plan"
    )
    build_yield_execution_plan = byep_mod.build_yield_execution_plan

    # Seed the universe — the prior search turn ran with constraints that
    # found these candidates. Pool "failed-slipstream-base-usdc-eth" is the
    # one the next exec call will hit and fail to build.
    universe = [
        _candidate(
            "failed-slipstream-base-usdc-eth",
            protocol="aerodrome-slipstream",
            chain="base",
            symbol="USDC-WETH",
            apy=18.0,
        ),
        _candidate(
            "compound-v3-base-usdc",
            protocol="compound-v3",
            chain="base",
            symbol="USDC",
            apy=5.5,
            executable=True,
        ),
        _candidate(
            "aave-v3-arb-usdc",
            protocol="aave-v3",
            chain="arbitrum",
            symbol="USDC",
            apy=4.2,
            executable=True,
        ),
        _candidate(
            "aave-v3-base-usdc",
            protocol="aave-v3",
            chain="base",
            symbol="USDC",
            apy=4.8,
            executable=True,
        ),
    ]
    remember_search_universe("sess-rc14", universe)

    # Force the adapter to raise so we exercise the recovery branch.
    class _FakeCapability:
        supported = True
        reason = ""

    class _FakeAdapter:
        async def build(self, *_a, **_kw):
            raise ValueError("Adapter could not resolve pool tokens for slipstream base USDC-WETH")

    class _FakeRegistry:
        def find(self, *, chain, protocol, action):
            return _FakeCapability()

        def adapter_for(self, *, chain, protocol, action):
            return _FakeAdapter()

    monkeypatch.setattr(byep_mod, "build_default_registry", lambda: _FakeRegistry())
    # Skip the pool-link gate (force the registry path).
    monkeypatch.setattr(
        byep_mod,
        "get_exec_capability",
        lambda *a, **kw: {"mode": "deterministic", "executable": True, "reason": ""},
    )

    ctx = ToolCtx(
        services=MagicMock(),
        user_id=1,
        wallet="0xdEAD000000000000000000000000000000000000",
        session_id="sess-rc14",
    )
    env = await build_yield_execution_plan(
        ctx,
        chain="base",
        protocol="aerodrome-slipstream",
        action="deposit_lp",
        asset_in="USDC",
        amount_in=137.42,  # non-placeholder amount; not 100 / 1000
        slippage_bps=50,
        extra={
            "pool_id": "failed-slipstream-base-usdc-eth",
            # Bypass the placeholder-amount guard — this test only
            # exercises the adapter-build-failure recovery branch.
            "amount_confirmed": True,
        },
    )
    assert isinstance(env, ToolEnvelope)
    assert env.ok is True
    plan = env.card_payload
    assert plan and "recovery" in plan
    recovery = plan["recovery"]
    # The single bug: alternatives was [] before RC14.
    assert recovery["alternatives"], (
        f"recovery.alternatives must NOT be empty after RC14. Got: {recovery!r}"
    )
    # The just-failed pool must NOT be in alternatives.
    pids = {a.get("pool_id") for a in recovery["alternatives"]}
    assert "failed-slipstream-base-usdc-eth" not in pids
    # At least one of the cached substitutes should appear.
    expected = {"compound-v3-base-usdc", "aave-v3-arb-usdc", "aave-v3-base-usdc"}
    assert pids & expected, (
        f"expected at least one of {expected} in alternatives, got {pids}"
    )
