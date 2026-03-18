from __future__ import annotations


def config() -> dict:
    return {
        "weights": {
            "protocol": 0.18,
            "market": 0.14,
            "apr": 0.22,
            "position": 0.14,
            "exit": 0.10,
            "behavior": 0.12,
            "chain": 0.04,
            "confidence": 0.06,
        },
        "net_apr_burden_rate": 0.08,
        "headline": "Farms need real carry durability to justify emissions and unwind risk.",
        "thesis": "Reward-heavy farms need sharper APR haircuts because incentives decay faster than headline APY suggests.",
    }
