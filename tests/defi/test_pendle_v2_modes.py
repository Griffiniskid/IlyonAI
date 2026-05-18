"""Pendle V2 per-mode dispatch + expiry blocker."""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.pendle_v2 import (
    PendleV2Adapter,
    SEL_ADD_LIQUIDITY_FROM_TOKEN,
    SEL_MINT_PY_FROM_TOKEN,
    SEL_REDEEM_PY_TO_TOKEN,
    SEL_SWAP_EXACT_PT_FOR_TOKEN,
    SEL_SWAP_TOKEN_FOR_PT,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _req(action: str | None = None, **over) -> YieldBuildRequest:
    extra = {"market": "0xabcabcabcabcabcabcabcabcabcabcabcabcabca"}
    if action:
        extra["action"] = action
    extra.update(over.pop("extra", {}))
    base = dict(
        chain="ethereum", protocol="pendle-v2", asset_in="USDC",
        amount_in=Decimal("100"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        slippage_bps=100,
        extra=extra,
    )
    base.update(over)
    return YieldBuildRequest(**base)


def test_default_action_routes_to_add_liquidity_mode():
    a = PendleV2Adapter()
    steps = _run(a.build(_req()))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "add_liquidity"
    assert SEL_ADD_LIQUIDITY_FROM_TOKEN in s.description
    assert "NEEDS_FRONTEND_SDK" in s.blocker_codes


def test_mint_py_action_routes_to_mint_py_selector():
    a = PendleV2Adapter()
    steps = _run(a.build(_req(action="mint_py")))
    assert steps[0].action == "mint_py"
    assert SEL_MINT_PY_FROM_TOKEN in steps[0].description


def test_swap_for_pt_action_routes_to_swap_selector():
    a = PendleV2Adapter()
    steps = _run(a.build(_req(action="swap_for_pt")))
    assert steps[0].action == "swap_for_pt"
    assert SEL_SWAP_TOKEN_FOR_PT in steps[0].description


def test_expired_market_returns_epoch_blocker():
    a = PendleV2Adapter()
    # 2020-01-01 — well in the past.
    expired_ts = 1577836800
    req = _req(extra={"market_expiry_ts": expired_ts})
    steps = _run(a.build(req))
    assert len(steps) == 1
    assert "PENDING_EPOCH_ENTRY" in steps[0].blocker_codes


def test_future_market_skips_epoch_blocker():
    a = PendleV2Adapter()
    future_ts = int(time.time()) + 86400 * 30  # 30 days out
    req = _req(extra={"market_expiry_ts": future_ts})
    steps = _run(a.build(req))
    assert "PENDING_EPOCH_ENTRY" not in steps[0].blocker_codes


def test_missing_market_raises():
    a = PendleV2Adapter()
    req = _req()
    req.extra.pop("market")
    with pytest.raises(ValueError, match="extra.market"):
        _run(a.build(req))


def test_unsupported_chain_raises():
    a = PendleV2Adapter()
    req = _req(chain="polygon")
    with pytest.raises(ValueError, match="Pendle V2 router not registered"):
        _run(a.build(req))


def test_selector_constants_pinned():
    """Regression pin: Pendle V4 router dispatcher selectors must not drift."""
    assert SEL_MINT_PY_FROM_TOKEN == "0xc81f847a"
    assert SEL_SWAP_TOKEN_FOR_PT == "0x594a88cc"
    assert SEL_ADD_LIQUIDITY_FROM_TOKEN == "0x9f9da99e"
    assert SEL_REDEEM_PY_TO_TOKEN == "0x47f1de22"
    assert SEL_SWAP_EXACT_PT_FOR_TOKEN == "0x594a88cc"


# ---------------------------------------------------------------------------
# V7-057 — 4-mode hosted-SDK calldata round-trip pins.
# Verifies Mint / Redeem / SwapExactTokenForPt / SwapExactPtForToken all
# round-trip a `tx.data` field through ExecutionStepV3.transaction.
# ---------------------------------------------------------------------------
from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest as _pytest  # noqa: E402  (re-import to avoid shadowing above)

from src.defi.execution.adapters.pendle_v2 import _QUOTE_CACHE  # noqa: E402


_USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
_USER = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_MARKET = "0xabcabcabcabcabcabcabcabcabcabcabcabcabca"


def _mock_session_ok(data_hex: str):
    body = {
        "routes": [{
            "tx": {"to": "0xRouterMode", "from": _USER, "value": "0", "data": data_hex},
            "outputs": [{"token": "0xPT", "amount": "1"}],
        }],
    }
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=body)
    resp_cm = AsyncMock()
    resp_cm.__aenter__.return_value = mock_resp
    resp_cm.__aexit__.return_value = None
    sess = AsyncMock()
    sess.get = lambda *a, **k: resp_cm
    sess_cm = AsyncMock()
    sess_cm.__aenter__.return_value = sess
    sess_cm.__aexit__.return_value = None
    return patch("aiohttp.ClientSession", return_value=sess_cm)


def _mode_req(action: str) -> YieldBuildRequest:
    extra = {
        "market": _MARKET,
        "action": action,
        "pt_address": "0xPT",
        "yt_address": "0xYT",
        "token_in_address": _USDC,
        "token_out_address": _USDC,
        "amount_in_wei": "1000000000",
        "receiver": _USER,
    }
    return YieldBuildRequest(
        chain="ethereum", protocol="pendle-v2", asset_in="USDC",
        amount_in=Decimal("1000"),
        user_address=_USER,
        slippage_bps=100,
        extra=extra,
    )


def test_mint_py_from_token_calldata_round_trips():
    _QUOTE_CACHE.clear()
    with _mock_session_ok("0xMINT00"):
        steps = _run(PendleV2Adapter().build(_mode_req("mint_py_from_token")))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "mint_py"
    assert s.transaction is not None
    assert s.transaction.data == "0xMINT00"
    assert s.snapshot["pendle_mode"] == "mintPyFromToken"
    assert s.snapshot["pendle_selector"] == SEL_MINT_PY_FROM_TOKEN


def test_redeem_py_to_token_calldata_round_trips():
    _QUOTE_CACHE.clear()
    with _mock_session_ok("0xREDEEM"):
        steps = _run(PendleV2Adapter().build(_mode_req("redeem_py_to_token")))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "redeem_py"
    assert s.transaction is not None
    assert s.transaction.data == "0xREDEEM"
    assert s.snapshot["pendle_mode"] == "redeemPyToToken"
    assert s.snapshot["pendle_selector"] == SEL_REDEEM_PY_TO_TOKEN


def test_swap_exact_token_for_pt_calldata_round_trips():
    _QUOTE_CACHE.clear()
    with _mock_session_ok("0xSWPIN0"):
        steps = _run(PendleV2Adapter().build(_mode_req("swap_exact_token_for_pt")))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "swap_for_pt"
    assert s.transaction is not None
    assert s.transaction.data == "0xSWPIN0"
    assert s.snapshot["pendle_mode"] == "swapExactTokenForPt"
    assert s.snapshot["pendle_selector"] == SEL_SWAP_TOKEN_FOR_PT


def test_swap_exact_pt_for_token_calldata_round_trips():
    _QUOTE_CACHE.clear()
    with _mock_session_ok("0xSWPOUT"):
        steps = _run(PendleV2Adapter().build(_mode_req("swap_exact_pt_for_token")))
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "swap_pt_for_token"
    assert s.transaction is not None
    assert s.transaction.data == "0xSWPOUT"
    assert s.snapshot["pendle_mode"] == "swapExactPtForToken"
    assert s.snapshot["pendle_selector"] == SEL_SWAP_EXACT_PT_FOR_TOKEN


def test_unknown_mode_raises_value_error():
    a = PendleV2Adapter()
    req = _req(action="bogus_mode_name")
    with _pytest.raises(ValueError, match="unknown action"):
        _run(a.build(req))
