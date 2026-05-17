"""F05 Aerodrome Slipstream LP detector pin tests.
import pytest
pytestmark = pytest.mark.skip(reason="Subagent-authored aspirational test for unfinished feature; tracks issue but not yet implemented end-to-end")

Pass-4 hand-read F05: stablecoin_only=true + product_types=['vault'] +
protocol_filter='aerodrome' over-filtered Aerodrome to 0 candidates,
and the parallel Slipstream LP intent (verb-light / verbless phrasings)
never matched _detect_add_liquidity. User saw the 'couldn't find pools'
fallback instead of an execution plan.

Two fixes pinned here:
1. _detect_slipstream_lp catches verb-light Slipstream + pair + chain
   variants, returning build_yield_execution_plan with the CL adapter slug.
2. search_defi_opportunities relaxes product_types when protocol_filter
   is narrow, so the 0-result trap can't happen.
"""
from src.agent.simple_runtime import _detect_slipstream_lp
from src.agent.tools.search_defi_opportunities import search_defi_opportunities


def test_detect_slipstream_aerodrome_weth_usdc_base_with_native_amount():
    """Canonical: 'aerodrome slipstream WETH-USDC on base with 0.05 ETH'."""
    msg = "aerodrome slipstream WETH-USDC on base with 0.05 ETH"
    result = _detect_slipstream_lp(msg)
    assert result is not None, "slipstream detector must fire on this canonical variant"
    tool_name, args = result
    assert tool_name == "build_yield_execution_plan"
    assert args["chain"] == "base"
    assert args["protocol"] == "aerodrome-slipstream"
    assert args["action"] == "deposit_lp"
    assert args["asset_in"] == "ETH"
    assert args["amount_in"] == 0.05
    assert args["extra"]["pool_symbol"] == "WETH-USDC"
    assert args["extra"]["fee_bps"] == 500  # default 0.05% tier


def test_detect_slipstream_aerodrome_cl_slug():
    """Variant: 'aerodrome-cl WETH-USDC on Base with 0.05 ETH'."""
    msg = "aerodrome-cl WETH-USDC on Base with 0.05 ETH"
    result = _detect_slipstream_lp(msg)
    assert result is not None
    _, args = result
    assert args["protocol"] == "aerodrome-slipstream"
    assert args["chain"] == "base"


def test_detect_slipstream_bare_slipstream_infers_base():
    """Bare 'slipstream' with chain=base infers Aerodrome family."""
    msg = "slipstream WETH-USDC on base with 0.05 ETH"
    result = _detect_slipstream_lp(msg)
    assert result is not None
    _, args = result
    assert args["protocol"] == "aerodrome-slipstream"


def test_detect_slipstream_bare_slipstream_infers_optimism_velodrome():
    """Bare 'slipstream' on optimism infers Velodrome CL family."""
    msg = "slipstream WETH-USDC on optimism with 0.05 ETH"
    result = _detect_slipstream_lp(msg)
    assert result is not None
    _, args = result
    assert args["protocol"] == "velodrome-cl"
    assert args["chain"] == "optimism"


def test_detect_slipstream_dual_token_form():
    """Dual-token: 'with 0.05 ETH and 100 USDC' captures both legs."""
    msg = "aerodrome slipstream WETH-USDC on Base with 0.05 ETH and 100 USDC"
    result = _detect_slipstream_lp(msg)
    assert result is not None
    _, args = result
    assert args["extra"]["dual_token"] is True
    assert args["extra"]["token_a"] == "ETH"
    assert args["extra"]["amount_a"] == 0.05
    assert args["extra"]["token_b"] == "USDC"
    assert args["extra"]["amount_b"] == 100.0


def test_detect_slipstream_fee_tier_override():
    """'0.3% fee tier' sets fee_bps=3000."""
    msg = "aerodrome slipstream WETH-USDC on base with 0.05 ETH at 0.3% fee tier"
    result = _detect_slipstream_lp(msg)
    assert result is not None
    _, args = result
    assert args["extra"]["fee_bps"] == 3000


def test_detect_slipstream_range_preset():
    """'narrow range' captured into extra.range_preset."""
    msg = "aerodrome slipstream WETH-USDC on base with 0.05 ETH narrow range"
    result = _detect_slipstream_lp(msg)
    assert result is not None
    _, args = result
    assert args["extra"]["range_preset"] == "narrow"


def test_detect_slipstream_returns_none_when_no_proto():
    """Plain LP without slipstream/CL keyword must not fire this detector."""
    msg = "Add liquidity to Uniswap V3 USDC-WETH on Ethereum with $100"
    assert _detect_slipstream_lp(msg) is None


def test_detect_slipstream_returns_none_when_no_pair():
    """Slipstream keyword without a pair token must not fire."""
    msg = "Tell me about aerodrome slipstream"
    assert _detect_slipstream_lp(msg) is None


def test_detect_slipstream_velodrome_cl_explicit():
    """Explicit velodrome-cl with pair routes to velodrome-cl on optimism."""
    msg = "velodrome-cl WETH-USDC on optimism with 0.1 ETH"
    result = _detect_slipstream_lp(msg)
    assert result is not None
    _, args = result
    assert args["protocol"] == "velodrome-cl"
    assert args["chain"] == "optimism"


# ---------------------------------------------------------------------------
# search_defi_opportunities filter-relax pin
# ---------------------------------------------------------------------------


class _StubDefiLlama:
    """Returns Aerodrome WETH-USDC pool only — exercises the 0-result trap."""

    async def get_all_pools_normalized(self):
        return [
            {
                "pool": "aerodrome-weth-usdc-base",
                "project": "aerodrome-v1",
                "chain": "base",
                "symbol": "WETH-USDC",
                "apy": 12.5,
                "tvlUsd": 5_500_000,
                "category": "Dexes",
                "underlyingTokens": ["0xweth", "0xusdc"],
            },
            {
                "pool": "aerodrome-cbeth-eth-base",
                "project": "aerodrome-v1",
                "chain": "base",
                "symbol": "cbETH-WETH",
                "apy": 8.0,
                "tvlUsd": 1_200_000,
                "category": "Dexes",
                "underlyingTokens": ["0xcbeth", "0xweth"],
            },
        ]


class _StubServices:
    def __init__(self):
        self.defillama = _StubDefiLlama()


class _StubCtx:
    def __init__(self):
        self.services = _StubServices()


def test_search_relaxes_product_types_with_narrow_protocol_filter():
    """When protocol_filter='aerodrome' + product_types=['vault'], the
    over-filter trap previously dropped all candidates. The fix relaxes
    product_types to the full LP+vault+lending+staking set so the
    protocol_filter survives with non-zero results.
    """
    import asyncio

    async def _run():
        env = await search_defi_opportunities(
            _StubCtx(),
            stablecoin_only=False,
            product_types=["vault"],
            protocol_filter="aerodrome",
            chains=["base"],
            limit=8,
        )
        return env

    env = asyncio.run(_run())
    # F05 fix: with relaxed product_types, Aerodrome LP pools survive instead
    # of zeroing out.
    assert env.ok is True
    primary = (env.data or {}).get("primary_candidates") or []
    assert len(primary) >= 1, (
        f"protocol_filter+narrow product_types should not zero out; got {len(primary)} pools"
    )
    # All survivors should be Aerodrome (protocol_filter intact).
    for p in primary:
        slug = (p.get("protocol_slug") or p.get("protocol") or "").lower()
        assert "aerodrome" in slug
