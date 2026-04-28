import pytest
from src.agent.decorator import decorate, DECORATION_MAP
from src.agent.tools._base import ToolCtx, ok_envelope
from src.api.schemas.agent import ToolEnvelope, SentinelBlock, ShieldBlock


class FakeOpp:
    async def summarize(self, pool):
        return {
            "sentinel": 92,
            "safety": 95,
            "durability": 90,
            "exit": 88,
            "confidence": 91,
            "risk_level": "LOW",
            "strategy_fit": "balanced",
            "flags": [],
        }


class FakeShield:
    async def verdict(self, mint):
        return {"verdict": "SAFE", "grade": "A", "reasons": []}


@pytest.mark.asyncio
async def test_pool_gets_sentinel_block():
    ctx = ToolCtx(
        services=type(
            "S",
            (),
            {"opportunity": FakeOpp(), "shield": FakeShield()},
        )(),
        user_id=1,
        wallet=None,
    )
    raw = ok_envelope(
        data={
            "protocol": "Aave",
            "chain": "Arbitrum",
            "asset": "USDC",
            "apy": "5.4%",
            "tvl": "$820M",
        },
        card_type="pool",
        card_payload={"protocol": "Aave"},
    )
    env = await decorate("find_liquidity_pool", raw.model_dump(), ctx)
    assert env.sentinel is not None
    assert env.sentinel.sentinel == 92


@pytest.mark.asyncio
async def test_token_price_gets_shield_block():
    ctx = ToolCtx(
        services=type(
            "S",
            (),
            {"opportunity": FakeOpp(), "shield": FakeShield()},
        )(),
        user_id=1,
        wallet=None,
    )
    raw = ok_envelope(
        data={"address": "0xABC", "price_usd": "1.00"},
        card_type="token",
    )
    env = await decorate("get_token_price", raw.model_dump(), ctx)
    assert env.shield is not None
    assert env.shield.verdict == "SAFE"


@pytest.mark.asyncio
async def test_failed_envelope_is_unchanged():
    ctx = ToolCtx(services=None, user_id=1, wallet=None)
    raw = ToolEnvelope(
        ok=False,
        data=None,
        card_type=None,
        card_id="test",
        card_payload=None,
        error={"code": "fail", "message": "boom"},
    )
    env = await decorate("find_liquidity_pool", raw, ctx)
    assert env.sentinel is None
    assert env.shield is None


@pytest.mark.asyncio
async def test_decorator_gracefully_ignores_service_errors():
    class BrokenOpp:
        async def summarize(self, pool):
            raise RuntimeError("service down")

    ctx = ToolCtx(
        services=type("S", (), {"opportunity": BrokenOpp(), "shield": None})(),
        user_id=1,
        wallet=None,
    )
    raw = ok_envelope(
        data={"protocol": "Aave"},
        card_type="pool",
    )
    # Must not raise -- decorator swallows errors
    env = await decorate("find_liquidity_pool", raw.model_dump(), ctx)
    assert env.ok
    assert env.sentinel is None


def test_decoration_map_covers_all_tools():
    expected = {
        "get_wallet_balance",
        "get_token_price",
        "simulate_swap",
        "build_swap_tx",
        "build_solana_swap",
        "get_defi_market_overview",
        "get_defi_analytics",
        "get_staking_options",
        "search_dexscreener_pairs",
        "find_liquidity_pool",
        "build_stake_tx",
        "build_deposit_lp_tx",
        "build_bridge_tx",
        "build_transfer_tx",
    }
    assert set(DECORATION_MAP.keys()) == expected
