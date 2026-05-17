"""Pin tests for V7-044 live DefiLlama price oracle + 60s LRU cache.

All HTTP is mocked at the aiohttp session level — no network I/O. Covers:
  1. Cache miss → mocked HTTP returns price → returns price
  2. Second call within 60s → returns cached value, no second HTTP fetch
  3. After 60s expiry → re-fetches
  4. 404 with no prior cache returns None
  5. 404 with prior cache returns the stale cached value
  6. HTTP timeout returns cached value if present, else None
  7. Malformed/empty body returns None
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pytest

import src.data.price_oracle as price_oracle
from src.data.price_oracle import (
    PRICE_CACHE_SECONDS,
    _clear_cache_for_tests,
    fetch_price_usd,
)


# ---------------------------------------------------------------------------
# Mock aiohttp session
# ---------------------------------------------------------------------------

class _MockResponse:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    async def __aenter__(self) -> "_MockResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def json(self) -> Any:
        return self._payload


class _RaiseCtx:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def __aenter__(self) -> "_RaiseCtx":
        raise self._exc

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _MockSession:
    """Records every .get() call. Returns whatever the configured callable yields."""

    def __init__(self, responder) -> None:
        self._responder = responder
        self.calls: list[str] = []

    def get(self, url: str, timeout: float = 0):
        self.calls.append(url)
        return self._responder(url)


CHAIN = "ethereum"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
COIN_KEY = f"{CHAIN}:{WETH.lower()}"


def _ok_body(price: float) -> Dict[str, Any]:
    return {"coins": {COIN_KEY: {"price": price, "symbol": "WETH", "decimals": 18}}}


@pytest.fixture(autouse=True)
def _reset_cache():
    _clear_cache_for_tests()
    yield
    _clear_cache_for_tests()


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cache_miss_fetches_and_returns_live_price():
    session = _MockSession(lambda _u: _MockResponse(_ok_body(2350.55)))
    price = _run(fetch_price_usd(CHAIN, WETH, session))
    assert price == pytest.approx(2350.55)
    assert len(session.calls) == 1
    # URL must hit DefiLlama coins endpoint with lowercase chain:addr.
    assert session.calls[0].endswith(f"/prices/current/{COIN_KEY}")


def test_second_call_within_60s_returns_cached_value_no_http():
    session = _MockSession(lambda _u: _MockResponse(_ok_body(2350.55)))
    first = _run(fetch_price_usd(CHAIN, WETH, session))
    second = _run(fetch_price_usd(CHAIN, WETH, session))
    assert first == second == pytest.approx(2350.55)
    # Cache hit must short-circuit HTTP entirely.
    assert len(session.calls) == 1


def test_cache_expiry_after_60s_triggers_refetch(monkeypatch):
    # First call at t=1000, second at t=1000 + PRICE_CACHE_SECONDS + 1.
    now = [1000.0]
    monkeypatch.setattr(price_oracle, "time", lambda: now[0])

    prices = iter([_ok_body(2350.55), _ok_body(2480.0)])
    session = _MockSession(lambda _u: _MockResponse(next(prices)))

    first = _run(fetch_price_usd(CHAIN, WETH, session))
    assert first == pytest.approx(2350.55)
    assert len(session.calls) == 1

    # Advance past TTL → next call should re-fetch.
    now[0] = 1000.0 + PRICE_CACHE_SECONDS + 1.0
    second = _run(fetch_price_usd(CHAIN, WETH, session))
    assert second == pytest.approx(2480.0)
    assert len(session.calls) == 2


def test_404_with_no_cache_returns_none():
    session = _MockSession(lambda _u: _MockResponse({"coins": {}}, status=404))
    price = _run(fetch_price_usd(CHAIN, WETH, session))
    assert price is None


def test_404_with_prior_cache_returns_stale(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(price_oracle, "time", lambda: now[0])

    # Prime cache.
    primed = _MockSession(lambda _u: _MockResponse(_ok_body(2350.55)))
    _run(fetch_price_usd(CHAIN, WETH, primed))

    # Advance past TTL and have DefiLlama 404.
    now[0] = 1000.0 + PRICE_CACHE_SECONDS + 5.0
    err = _MockSession(lambda _u: _MockResponse({}, status=404))
    price = _run(fetch_price_usd(CHAIN, WETH, err))
    # Stale-but-better-than-nothing fallback.
    assert price == pytest.approx(2350.55)


def test_timeout_with_cache_returns_cached_else_none(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(price_oracle, "time", lambda: now[0])

    # No cache yet → timeout returns None.
    boom = _MockSession(lambda _u: _RaiseCtx(asyncio.TimeoutError()))
    assert _run(fetch_price_usd(CHAIN, WETH, boom)) is None

    # Prime cache.
    primed = _MockSession(lambda _u: _MockResponse(_ok_body(2350.55)))
    _run(fetch_price_usd(CHAIN, WETH, primed))

    # Advance past TTL and timeout → stale cache wins.
    now[0] = 1000.0 + PRICE_CACHE_SECONDS + 5.0
    assert _run(fetch_price_usd(CHAIN, WETH, boom)) == pytest.approx(2350.55)


def test_malformed_body_returns_none():
    # 200 OK but no matching coin key → treated as miss, no cache write.
    session = _MockSession(lambda _u: _MockResponse({"coins": {"other:0xdead": {"price": 1.0}}}))
    assert _run(fetch_price_usd(CHAIN, WETH, session)) is None


def test_chain_and_addr_are_case_insensitive():
    session = _MockSession(lambda _u: _MockResponse(_ok_body(2350.55)))
    price = _run(fetch_price_usd("Ethereum", WETH.upper(), session))
    assert price == pytest.approx(2350.55)
    # URL is normalized to lowercase.
    assert session.calls[0].endswith(f"/prices/current/{COIN_KEY}")
