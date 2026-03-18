from __future__ import annotations


def config() -> dict:
    return {
        "weights": {
            "protocol": 0.18,
            "market": 0.12,
            "apr": 0.18,
            "position": 0.18,
            "exit": 0.12,
            "behavior": 0.10,
            "chain": 0.04,
            "confidence": 0.08,
        },
        "net_apr_burden_rate": 0.06,
        "headline": "Vaults add strategy-path risk on top of protocol and market quality.",
        "thesis": "Vault returns deserve extra scrutiny because manager logic and turnover can change the risk path.",
    }
