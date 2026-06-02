"""B11 — USDC/WETH on Ethereum canonical fallback pin tests.

Pass-4 hand-read caught: find_liquidity_pool({token_a:USDC, token_b:WETH,
chain:ethereum}) returned ok:true but the agent emitted
'pool_not_found: No liquidity pools found for USDC/WETH'. Tracing the tool
showed the DefiLlama/DexScreener fallbacks could return empty for the most
liquid pool on Ethereum — and the empty payload then degraded to
pool_not_found.

Fix: hardcode a canonical Uniswap V3 0.05% pool
(0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640) as a last-resort fallback for
the canonical USDC/WETH ethereum pair. These tests pin the fallback so the
'liquid pool reports not-found' regression can't return.
"""
from __future__ import annotations

import pytest

from src.agent.tools.pool_find import find_liquidity_pool


class _EmptyServices:
    """Services bag with no defillama/dexscreener — forces the canonical
    fallback path."""
    pass


class _Ctx:
    def __init__(self):
        self.services = _EmptyServices()


@pytest.mark.asyncio
async def test_usdc_weth_ethereum_returns_canonical_univ3_pool():
    ctx = _Ctx()
    env = await find_liquidity_pool(ctx, token_a="USDC", token_b="WETH", chain="ethereum")
    assert env.ok is True, f"expected ok envelope, got: {env}"
    assert env.data is not None
    assert env.data["count"] >= 1
    assert env.data["source"] == "canonical-fallback"
    pool = env.data["pools"][0]
    assert pool["pair_address"].lower() == "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
    assert pool["protocol"] == "uniswap-v3"
    assert pool["chain"] == "ethereum"
    assert pool["liquidity_usd"] > 0


@pytest.mark.asyncio
async def test_weth_usdc_reversed_order_also_works():
    ctx = _Ctx()
    env = await find_liquidity_pool(ctx, token_a="WETH", token_b="USDC", chain="ethereum")
    assert env.ok is True
    assert env.data["count"] >= 1
    pool = env.data["pools"][0]
    assert pool["pair_address"].lower() == "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"


@pytest.mark.asyncio
async def test_usdc_eth_native_alias_also_works():
    ctx = _Ctx()
    env = await find_liquidity_pool(ctx, token_a="USDC", token_b="ETH", chain="ethereum")
    assert env.ok is True
    assert env.data["count"] >= 1
    pool = env.data["pools"][0]
    assert pool["pair_address"].lower() == "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"


@pytest.mark.asyncio
async def test_non_canonical_pair_still_errors():
    """Sanity: the canonical fallback only fires for USDC/WETH on Ethereum.
    A random pair must still error (err_envelope normalizes the raw
    `pool_not_found` code to the canonical UNSUPPORTED_ADAPTER)."""
    ctx = _Ctx()
    env = await find_liquidity_pool(ctx, token_a="FOO", token_b="BAR", chain="ethereum")
    assert env.ok is False
    assert env.error.code == "UNSUPPORTED_ADAPTER"


@pytest.mark.asyncio
async def test_canonical_pair_wrong_chain_still_errors():
    """Sanity: USDC/WETH on a non-ethereum chain shouldn't get the canonical
    ethereum fallback."""
    ctx = _Ctx()
    env = await find_liquidity_pool(ctx, token_a="USDC", token_b="WETH", chain="polygon")
    # Polygon USDC/WETH is NOT 0x88e6...5640 — that's an ethereum mainnet
    # address. Must error rather than mis-attribute (err_envelope normalizes
    # the raw `pool_not_found` code to the canonical UNSUPPORTED_ADAPTER).
    assert env.ok is False
    assert env.error.code == "UNSUPPORTED_ADAPTER"
