"""Pin tests for V7-034 Merkl rewards live pricing client.

All HTTP is mocked at the session level — no network I/O. Tests cover:
  1. fetch_merkl_rewards parses /opportunity into normalized reward dicts
  2. price_reward_token decodes DefiLlama /prices/current
  3. compute_merkl_apr returns non-zero given rewards + prices + TVL
  4. Empty rewards short-circuit to 0.0
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pytest

from src.data.merkl_client import (
    MERKL_BASE_URL,
    compute_merkl_apr,
    fetch_merkl_rewards,
    price_reward_token,
)


class _MockResponse:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    async def __aenter__(self) -> "_MockResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        return None

    async def json(self) -> Any:
        return self._payload


class _MockSession:
    """Routes GETs by URL substring to a registered payload."""

    def __init__(self, routes: Dict[str, Any]) -> None:
        self._routes = routes
        self.calls: list[tuple[str, Optional[Dict[str, Any]]]] = []

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, timeout: float = 0):
        self.calls.append((url, params))
        for pattern, payload in self._routes.items():
            if pattern in url:
                if isinstance(payload, Exception):
                    raise payload
                if isinstance(payload, tuple):
                    body, status = payload
                    return _MockResponse(body, status=status)
                return _MockResponse(payload)
        return _MockResponse({}, status=404)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ARB = "0x912CE59144191C1204E64559FE8253a0e49E6548"
GRAIL = "0x3d9907F9a368ad0a51Be60f7Da3b97cf940982D8"
POOL = "0x2f5e87C9312fa29aed5c179E456625D79015299c"
CHAIN_ID = 42161  # arbitrum

MERKL_PAYLOAD = {
    "opp-1": {
        "apr": 5.0,
        "rewardsRecord": {
            "breakdowns": [
                {
                    "token": {"address": ARB, "symbol": "ARB"},
                    "apr": 3.5,
                    "dailyRewards": 100.0,
                },
                {
                    "token": {"address": GRAIL, "symbol": "GRAIL"},
                    "apr": 1.5,
                    "dailyRewards": 2.0,
                },
            ]
        },
    }
}

LLAMA_ARB = {"coins": {f"arbitrum:{ARB.lower()}": {"price": 0.80, "symbol": "ARB"}}}
LLAMA_GRAIL = {"coins": {f"arbitrum:{GRAIL.lower()}": {"price": 1500.0, "symbol": "GRAIL"}}}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fetch_merkl_rewards_normalizes_breakdowns():
    session = _MockSession({"opportunity": MERKL_PAYLOAD})
    rewards = _run(fetch_merkl_rewards(CHAIN_ID, POOL, session))

    assert isinstance(rewards, list)
    assert len(rewards) == 2

    by_sym = {r["token_symbol"]: r for r in rewards}
    assert by_sym["ARB"]["token_addr"] == ARB
    assert by_sym["ARB"]["daily_token_amount"] == 100.0
    assert by_sym["ARB"]["apr_pct"] == 3.5
    assert by_sym["GRAIL"]["daily_token_amount"] == 2.0
    assert by_sym["GRAIL"]["price_usd"] is None  # not priced yet

    # Confirm we hit Merkl's /opportunity endpoint.
    assert any("opportunity" in url for url, _ in session.calls)
    assert any(MERKL_BASE_URL in url for url, _ in session.calls)


def test_price_reward_token_returns_float_from_defillama():
    session = _MockSession({f"arbitrum:{ARB.lower()}": LLAMA_ARB})
    price = _run(price_reward_token(ARB, CHAIN_ID, session))
    assert price == 0.80


def test_price_reward_token_returns_none_when_unknown_chain():
    session = _MockSession({})
    price = _run(price_reward_token(ARB, 999_999, session))
    assert price is None


def test_compute_merkl_apr_nonzero_with_rewards_and_prices():
    routes = {
        "opportunity": MERKL_PAYLOAD,
        f"arbitrum:{ARB.lower()}": LLAMA_ARB,
        f"arbitrum:{GRAIL.lower()}": LLAMA_GRAIL,
    }
    session = _MockSession(routes)
    tvl_usd = 1_000_000.0

    apr = _run(compute_merkl_apr(CHAIN_ID, POOL, tvl_usd, session))

    # Expected daily USD = 100*0.8 + 2*1500 = 80 + 3000 = 3080
    # APR = 3080 * 365 / 1_000_000 * 100 = 112.42 %
    assert apr > 0.0
    assert 100.0 < apr < 130.0


def test_compute_merkl_apr_empty_rewards_returns_zero():
    # Merkl returns no opportunities for unknown pool.
    session = _MockSession({"opportunity": {}})
    apr = _run(compute_merkl_apr(CHAIN_ID, POOL, 1_000_000.0, session))
    assert apr == 0.0


def test_compute_merkl_apr_falls_back_to_merkl_apr_when_unpriced():
    # No DefiLlama price routes registered → fallback to Merkl-reported APR.
    session = _MockSession({"opportunity": MERKL_PAYLOAD})
    apr = _run(compute_merkl_apr(CHAIN_ID, POOL, 1_000_000.0, session))
    # 3.5 + 1.5 = 5.0
    assert apr == pytest.approx(5.0)


def test_import_surface_exports_required_symbols():
    """Exit criterion 2: import surface must be stable."""
    from src.data.merkl_client import fetch_merkl_rewards, compute_merkl_apr  # noqa: F401
