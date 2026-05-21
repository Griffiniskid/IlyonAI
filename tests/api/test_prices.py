"""Pin test for /api/v1/prices/simple — CoinGecko proxy with cache + fallback.

Frontend ticker bars (MarketTickerBar, SidebarMarketList, MainApp price
poller) all route through this endpoint instead of api.coingecko.com
directly (Cloudflare blocks `/api/coingecko/*` at the edge; direct browser
calls are CORS-blocked).

Asserts:
  1. Empty `ids` → 200 with {}
  2. Upstream success → 200 with mapped data (x-cache header present)
  3. Upstream failure → 200 with {} (NEVER 5xx — frontend wraps in try/catch
     but degrading silently is still the contract here)
  4. Repeat call within TTL → x-cache: HIT (not re-fetched)
"""
from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.app import create_api_app


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the module-level cache between tests."""
    from src.api.routes import prices as prices_module
    prices_module._CACHE.clear()
    yield
    prices_module._CACHE.clear()


@pytest.mark.asyncio
async def test_simple_price_empty_ids_returns_empty():
    app = create_api_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/v1/prices/simple")
        assert r.status == 200
        body = await r.json()
        assert body == {}


@pytest.mark.asyncio
async def test_simple_price_proxies_and_caches():
    """Successful upstream call returns data; second call hits cache."""
    fake_price_client = MagicMock()
    fake_price_client.get_token_price = AsyncMock(
        return_value={"bitcoin": {"usd": 77000.0, "usd_24h_change": 1.5}},
    )
    fake_services = MagicMock()
    fake_services.price = fake_price_client

    app = create_api_app()
    async with TestClient(TestServer(app)) as client:
        with patch("src.agent.services.get_agent_services", AsyncMock(return_value=fake_services)):
            # First call → MISS
            r1 = await client.get(
                "/api/v1/prices/simple?ids=bitcoin&vs_currencies=usd&include_24hr_change=true",
            )
            assert r1.status == 200
            assert r1.headers.get("x-cache") == "MISS"
            body1 = await r1.json()
            assert body1 == {"bitcoin": {"usd": 77000.0, "usd_24h_change": 1.5}}

            # Second call within TTL → HIT (upstream not called again)
            fake_price_client.get_token_price.reset_mock()
            r2 = await client.get(
                "/api/v1/prices/simple?ids=bitcoin&vs_currencies=usd&include_24hr_change=true",
            )
            assert r2.status == 200
            assert r2.headers.get("x-cache") == "HIT"
            assert await r2.json() == body1
            assert fake_price_client.get_token_price.call_count == 0


@pytest.mark.asyncio
async def test_simple_price_returns_empty_on_upstream_failure_not_5xx():
    """Upstream failure must NOT propagate as 5xx — frontend depends on this."""
    fake_price_client = MagicMock()
    fake_price_client.get_token_price = AsyncMock(side_effect=RuntimeError("rate limited"))
    fake_services = MagicMock()
    fake_services.price = fake_price_client

    app = create_api_app()
    async with TestClient(TestServer(app)) as client:
        with patch("src.agent.services.get_agent_services", AsyncMock(return_value=fake_services)):
            r = await client.get("/api/v1/prices/simple?ids=bitcoin&vs_currencies=usd")
            assert r.status == 200
            assert r.headers.get("x-cache") == "EMPTY"
            assert await r.json() == {}


@pytest.mark.asyncio
async def test_simple_price_serves_stale_when_upstream_fails_after_hit():
    """If cached and upstream fails on refresh, serve STALE rather than EMPTY."""
    from src.api.routes import prices as prices_module
    import time as _time

    # Pre-warm cache (bypassing the endpoint to avoid TestClient mock pyramid)
    key = prices_module._cache_key("bitcoin", "usd", False)
    prices_module._CACHE[key] = (_time.monotonic() - 10, {"bitcoin": {"usd": 50000.0}})

    fake_price_client = MagicMock()
    fake_price_client.get_token_price = AsyncMock(side_effect=RuntimeError("down"))
    fake_services = MagicMock()
    fake_services.price = fake_price_client

    app = create_api_app()
    async with TestClient(TestServer(app)) as client:
        with patch("src.agent.services.get_agent_services", AsyncMock(return_value=fake_services)):
            # Force expiry by bumping TTL window
            with patch("src.api.routes.prices._CACHE_TTL", 0.0):
                r = await client.get("/api/v1/prices/simple?ids=bitcoin&vs_currencies=usd")
                assert r.status == 200
                assert r.headers.get("x-cache") == "STALE"
                assert await r.json() == {"bitcoin": {"usd": 50000.0}}
