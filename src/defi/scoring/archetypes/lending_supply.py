from __future__ import annotations


def config() -> dict:
    return {
        "weights": {
            "protocol": 0.22,
            "market": 0.08,
            "apr": 0.16,
            "position": 0.22,
            "exit": 0.16,
            "behavior": 0.06,
            "chain": 0.04,
            "confidence": 0.06,
        },
        "net_apr_burden_rate": 0.04,
        "headline": "Lending quality is mostly reserve health, protocol integrity, and exit capacity.",
        "thesis": "Supply APR is only attractive when utilization and reserve stress stay orderly.",
    }
