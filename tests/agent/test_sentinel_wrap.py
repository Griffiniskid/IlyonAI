from src.agent.tools._base import ok_envelope
import pytest

from src.agent.tools.sentinel_wrap import (
    attach_pool_score,
    attach_transaction_shield,
    enrich_tool_envelope,
    sentinel_decorator,
)


def test_attach_pool_score_adds_sentinel_sidecar():
    env = ok_envelope(
        data={
            "project": "aave-v3",
            "symbol": "USDC",
            "chain": "Arbitrum",
            "tvlUsd": 900_000_000,
            "apy": 4.2,
        },
        card_type="pool",
        card_payload={
            "protocol": "aave-v3",
            "asset": "USDC",
            "chain": "Arbitrum",
            "apy": "4.2%",
            "tvl": "$900M",
        },
    )

    wrapped = attach_pool_score(env)

    assert wrapped.sentinel is not None
    assert wrapped.sentinel.sentinel >= 82
    assert wrapped.card_payload["sentinel"]["sentinel"] == wrapped.sentinel.sentinel


def test_attach_transaction_shield_adds_shield_sidecar():
    env = ok_envelope(data={"slippage_bps": 800, "spender": "UnknownRouter"}, card_type=None, card_payload=None)

    wrapped = attach_transaction_shield(env)

    assert wrapped.shield is not None
    assert wrapped.shield.verdict == "RISKY"


@pytest.mark.asyncio
async def test_sentinel_decorator_scores_route_tool_envelope():
    async def fake_tool(_ctx, *, token_out):
        return ok_envelope(
            data={"router": "Enso", "token_in": "ETH", "token_out": token_out, "slippage_bps": 50},
            card_type="swap_quote",
            card_payload={"pay": {"symbol": "ETH"}, "receive": {"symbol": token_out}, "rate": "1", "router": "Enso", "price_impact_pct": 0.1},
        )

    wrapped = sentinel_decorator(target="route")(fake_tool)
    env = await wrapped(object(), token_out="USDC")

    assert env.sentinel is not None
    assert env.shield is not None
    assert env.card_payload["sentinel"]["sentinel"] == env.sentinel.sentinel
    assert env.scoring_inputs["target"] == "route"


def test_enrich_tool_envelope_scores_staking_card_from_first_option():
    env = ok_envelope(
        data={
            "staking_options": [
                {"protocol": "aave-v3", "project": "aave-v3", "symbol": "USDC", "chain": "Arbitrum", "tvlUsd": 900_000_000, "apy": 4.8}
            ]
        },
        card_type="stake",
        card_payload={"protocol": "aave-v3", "asset": "USDC", "apy": "4.8%"},
    )

    enriched = enrich_tool_envelope("get_staking_options", env)

    assert enriched.sentinel is not None
    assert enriched.card_payload["sentinel"]["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
