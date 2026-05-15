"""Phase 4 lifecycle — V3 NFT decrease/collect/close encoding."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.uniswap_v3_nft import UniswapV3NFTAdapter


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def adapter():
    return UniswapV3NFTAdapter()


def _build(adapter, action: str, **extras):
    req = YieldBuildRequest(
        chain="ethereum", protocol="uniswap-v3",
        asset_in="", amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": action, "token_id": 12345, "liquidity": 1_000_000_000_000, **extras},
    )
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(adapter.build(req))
    finally:
        loop.close()


def test_decrease_liquidity_emits_multicall(adapter):
    steps = _build(adapter, "decrease_liquidity")
    assert len(steps) == 1
    s = steps[0]
    assert s.action == "decrease_liquidity"
    # NFP on Ethereum is the canonical Uniswap NPM.
    assert s.transaction.to.lower() == "0xc36442b4a4522e871399cd717abdd847ab11fe88"
    # Multicall selector starts the calldata.
    assert s.transaction.data.startswith("0xac9650d8")
    # Inner decreaseLiquidity selector embedded.
    assert "0c49ccbe" in s.transaction.data
    # Inner collect selector embedded.
    assert "fc6f7865" in s.transaction.data


def test_collect_only_skips_decrease(adapter):
    steps = _build(adapter, "collect", liquidity=0)
    assert len(steps) == 1
    data = steps[0].transaction.data
    # No decreaseLiquidity sub-call.
    assert "0c49ccbe" not in data
    # collect selector present.
    assert "fc6f7865" in data
    # No burn.
    assert "42966c68" not in data


def test_close_position_includes_burn(adapter):
    steps = _build(adapter, "close_position")
    data = steps[0].transaction.data
    # All three inner selectors present.
    assert "0c49ccbe" in data
    assert "fc6f7865" in data
    assert "42966c68" in data
    assert steps[0].action == "close_position"


def test_lifecycle_requires_token_id(adapter):
    req = YieldBuildRequest(
        chain="ethereum", protocol="uniswap-v3",
        asset_in="", amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "decrease_liquidity", "liquidity": 100},
    )
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(ValueError, match="token_id"):
            loop.run_until_complete(adapter.build(req))
    finally:
        loop.close()


def test_lifecycle_decrease_requires_liquidity(adapter):
    req = YieldBuildRequest(
        chain="ethereum", protocol="uniswap-v3",
        asset_in="", amount_in=Decimal("0"),
        user_address="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        extra={"action": "decrease_liquidity", "token_id": 1, "liquidity": 0},
    )
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(ValueError, match="liquidity"):
            loop.run_until_complete(adapter.build(req))
    finally:
        loop.close()
