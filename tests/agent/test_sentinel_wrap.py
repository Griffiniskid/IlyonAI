from src.agent.tools._base import ok_envelope
from src.agent.tools.sentinel_wrap import attach_pool_score, attach_transaction_shield


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
