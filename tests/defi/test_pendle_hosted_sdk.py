"""Pin tests for Pendle Hosted SDK `/v2/sdk/{chainId}/convert` integration.

Covers:
  * _fetch_pendle_convert happy-path returns parsed JSON.
  * 5xx / 4xx / timeout fall through to None.
  * _amount_bucket / _cache_key stability for cache-hit invariants.
  * _tokens_out_for branches per action.
  * PendleV2Adapter.build wires signable tx.to/data/value when the hosted
    SDK responds and falls back to NEEDS_FRONTEND_SDK when it does not.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.pendle_v2 import (
    PendleV2Adapter,
    _QUOTE_CACHE,
    _amount_bucket,
    _cache_key,
    _fetch_pendle_convert,
    _tokens_out_for,
)


# ---------------------------------------------------------------------------
# aiohttp ClientSession mock helper — patches the constructor to return an
# async-ctx that yields a session whose .get returns an async-ctx response.
# ---------------------------------------------------------------------------

def _mock_session(*, status: int, body: dict | None = None, raise_exc: Exception | None = None):
    """Return a context-manager that patches `aiohttp.ClientSession`."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    if body is not None:
        mock_resp.json = AsyncMock(return_value=body)

    resp_cm = AsyncMock()
    resp_cm.__aenter__.return_value = mock_resp
    resp_cm.__aexit__.return_value = None

    sess = AsyncMock()
    if raise_exc is not None:
        def _raiser(*_a, **_k):
            raise raise_exc
        sess.get = _raiser
    else:
        sess.get = lambda *a, **k: resp_cm

    sess_cm = AsyncMock()
    sess_cm.__aenter__.return_value = sess
    sess_cm.__aexit__.return_value = None
    return patch("aiohttp.ClientSession", return_value=sess_cm)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Bucketing / cache key
# ---------------------------------------------------------------------------

def test_amount_bucket_zero_and_small():
    assert _amount_bucket(0) == 0
    assert _amount_bucket(-5) == 0
    assert _amount_bucket(1) == 1
    assert _amount_bucket(99) == 99


def test_amount_bucket_three_sig_figs():
    # 1_234_567 → top 3 sig-figs → 1_230_000
    assert _amount_bucket(1_234_567) == 1_230_000
    assert _amount_bucket(1_999_999) == 1_990_000


def test_cache_key_normalises_addresses():
    a = _cache_key(1, "0xAaA", "swap_for_pt", "0xBbB", 1_000_000, 100)
    b = _cache_key(1, "0xaaa", "swap_for_pt", "0xbbb", 1_000_000, 100)
    assert a == b


# ---------------------------------------------------------------------------
# tokens_out per mode
# ---------------------------------------------------------------------------

def test_tokens_out_mint_py_concatenates_pt_yt():
    extra = {"pt_address": "0xPT", "yt_address": "0xYT", "market": "0xMK"}
    assert _tokens_out_for("mint_py", extra) == "0xPT,0xYT"
    assert _tokens_out_for("mintPyFromToken", extra) == "0xPT,0xYT"


def test_tokens_out_swap_for_pt_returns_pt_only():
    extra = {"pt_address": "0xPT", "market": "0xMK"}
    assert _tokens_out_for("swap_for_pt", extra) == "0xPT"
    assert _tokens_out_for("swapTokenForPt", extra) == "0xPT"


def test_tokens_out_add_liquidity_returns_market():
    extra = {"market": "0xMK"}
    assert _tokens_out_for("add_liquidity", extra) == "0xMK"
    assert _tokens_out_for("addLiquidityFromToken", extra) == "0xMK"


def test_tokens_out_unknown_action_returns_none():
    assert _tokens_out_for("foo", {"market": "0xMK"}) is None


def test_tokens_out_missing_required_returns_none():
    assert _tokens_out_for("mint_py", {"market": "0xMK"}) is None  # missing pt/yt
    assert _tokens_out_for("swap_for_pt", {}) is None


# ---------------------------------------------------------------------------
# _fetch_pendle_convert success / failure paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pendle_convert_success():
    body = {
        "action": "swapExactTokenForPt",
        "routes": [{
            "contractParamInfo": {"method": "swapExactTokenForPt", "contractCallParams": []},
            "tx": {"to": "0xRouter", "from": "0xUser", "value": "0", "data": "0xabcdef"},
            "outputs": [{"token": "0xPT", "amount": "12345"}],
            "data": {"priceImpact": 0.01},
        }],
    }
    with _mock_session(status=200, body=body):
        out = await _fetch_pendle_convert(
            1,
            tokens_in="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            amounts_in="1000000000",
            tokens_out="0xPT",
            receiver="0xUser",
            slippage=0.01,
        )
    assert out is not None
    assert out["routes"][0]["tx"]["data"] == "0xabcdef"


@pytest.mark.asyncio
async def test_pendle_convert_5xx_returns_none():
    with _mock_session(status=502):
        out = await _fetch_pendle_convert(
            1,
            tokens_in="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            amounts_in="1000000000",
            tokens_out="0xPT",
            receiver="0xUser",
            slippage=0.01,
        )
    assert out is None


@pytest.mark.asyncio
async def test_pendle_convert_4xx_returns_none():
    with _mock_session(status=400):
        out = await _fetch_pendle_convert(
            1,
            tokens_in="0xUSDC", amounts_in="1", tokens_out="0xPT",
            receiver="0xUser", slippage=0.01,
        )
    assert out is None


@pytest.mark.asyncio
async def test_pendle_convert_timeout_returns_none():
    with _mock_session(status=200, raise_exc=asyncio.TimeoutError()):
        out = await _fetch_pendle_convert(
            1,
            tokens_in="0xUSDC", amounts_in="1", tokens_out="0xPT",
            receiver="0xUser", slippage=0.01,
        )
    assert out is None


@pytest.mark.asyncio
async def test_pendle_convert_client_error_returns_none():
    with _mock_session(status=200, raise_exc=aiohttp.ClientError("boom")):
        out = await _fetch_pendle_convert(
            1,
            tokens_in="0xUSDC", amounts_in="1", tokens_out="0xPT",
            receiver="0xUser", slippage=0.01,
        )
    assert out is None


# ---------------------------------------------------------------------------
# PendleV2Adapter.build end-to-end: SDK success vs fallback
# ---------------------------------------------------------------------------

_USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
_USER = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_MARKET = "0xabcabcabcabcabcabcabcabcabcabcabcabcabca"


def _build_req(action: str = "swap_for_pt", **over) -> YieldBuildRequest:
    extra = {
        "market": _MARKET,
        "action": action,
        "pt_address": "0xPT",
        "yt_address": "0xYT",
        "token_in_address": _USDC,
        "amount_in_wei": "1000000000",
        "receiver": _USER,
    }
    extra.update(over.pop("extra", {}))
    return YieldBuildRequest(
        chain="ethereum",
        protocol="pendle-v2",
        asset_in="USDC",
        amount_in=Decimal("1000"),
        user_address=_USER,
        slippage_bps=100,
        extra=extra,
    )


def test_build_sdk_success_returns_signable_step():
    _QUOTE_CACHE.clear()
    body = {
        "routes": [{
            "tx": {"to": "0xRouter", "from": _USER, "value": "0", "data": "0xfeedface"},
            "outputs": [{"token": "0xPT", "amount": "42"}],
        }],
    }
    with _mock_session(status=200, body=body):
        steps = _run(PendleV2Adapter().build(_build_req(action="swap_for_pt")))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "swap_for_pt"
    assert s.blocker_codes == []
    assert s.transaction is not None
    assert s.transaction.to == "0xRouter"
    assert s.transaction.data == "0xfeedface"
    assert s.transaction.value == "0"
    assert s.snapshot is not None
    assert s.snapshot["source"] == "pendle_hosted_sdk"
    # V7-057 — canonical Pendle V4 router method name.
    assert s.snapshot["pendle_mode"] == "swapExactTokenForPt"


def test_build_sdk_failure_falls_back_to_blocker():
    _QUOTE_CACHE.clear()
    with _mock_session(status=502):
        steps = _run(PendleV2Adapter().build(_build_req(action="swap_for_pt")))
    assert len(steps) == 1
    s = steps[0]
    assert "NEEDS_FRONTEND_SDK" in s.blocker_codes
    assert s.transaction is None


def test_build_missing_token_in_skips_sdk_falls_back():
    _QUOTE_CACHE.clear()
    req = _build_req(action="add_liquidity")
    req.extra.pop("token_in_address")
    # No HTTP should be issued — but if it is, we'd still pass since body would
    # need to be set. Patch with a 500 to make accidental fetches fail loudly.
    with _mock_session(status=500):
        steps = _run(PendleV2Adapter().build(req))
    assert "NEEDS_FRONTEND_SDK" in steps[0].blocker_codes


def test_build_caches_sdk_response_per_key():
    _QUOTE_CACHE.clear()
    body = {
        "routes": [{
            "tx": {"to": "0xR", "from": _USER, "value": "0", "data": "0xCAFE"},
            "outputs": [],
        }],
    }
    with _mock_session(status=200, body=body):
        steps1 = _run(PendleV2Adapter().build(_build_req(action="add_liquidity")))
    # Second call should be cache-hit — patch in a 500 so any real fetch fails.
    with _mock_session(status=500):
        steps2 = _run(PendleV2Adapter().build(_build_req(action="add_liquidity")))
    assert steps1[0].transaction is not None
    assert steps2[0].transaction is not None
    assert steps1[0].transaction.data == steps2[0].transaction.data == "0xCAFE"
