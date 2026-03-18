from __future__ import annotations


def config() -> dict:
    return {
        "weights": {
            "protocol": 0.20,
            "market": 0.18,
            "apr": 0.18,
            "position": 0.14,
            "exit": 0.14,
            "behavior": 0.08,
            "chain": 0.04,
            "confidence": 0.04,
        },
        "net_apr_burden_rate": 0.05,
        "headline": "LP risk-reward depends on structural quality, exits, and durable carry.",
        "thesis": "LP setups only work when the fee surface can survive risk and behavior stress.",
    }
