"""Portfolio snapshot builder using the wallet assistant balance function."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

class PortfolioPosition(BaseModel):
    protocol: str
    token: str
    chain: str
    usd_value: float
    apy: float
    sentinel: int


class PortfolioSnapshot(BaseModel):
    user_id: int
    positions: list[PortfolioPosition] = Field(default_factory=list)

    @property
    def total_usd(self) -> float:
        return sum(position.usd_value for position in self.positions)

    @property
    def blended_sentinel(self) -> int | None:
        total = self.total_usd
        if total <= 0:
            return None
        return round(sum(position.sentinel * position.usd_value for position in self.positions) / total)


async def snapshot_from_user(wallet_address: str) -> list[dict[str, Any]]:
    """Return a list of position dicts {token, usd, apy, sentinel, chain_id}.

    Uses get_smart_wallet_balance in-process if available; falls back to
    empty list when the wallet address is missing.
    """
    if not wallet_address:
        return []

    from src.agent.tools._assistant_bridge import parse_assistant_json

    from IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent import (
        get_smart_wallet_balance,
    )

    raw = get_smart_wallet_balance(wallet_address, user_address=wallet_address,
                                   solana_address="")
    try:
        parsed = parse_assistant_json(raw)
    except Exception:
        return []

    positions: list[dict[str, Any]] = []
    by_chain = parsed.get("by_chain") or parsed.get("chains") or {}
    for chain_id_str, amount in by_chain.items():
        positions.append({
            "token": "NATIVE",
            "chain_id": _resolve_chain_id(chain_id_str),
            "usd": _try_float(amount, 0.0),
            "apy": 0.0,
            "sentinel": 50,
        })

    tokens = parsed.get("tokens") or parsed.get("positions") or []
    for t in tokens:
        if isinstance(t, dict):
            symbol = t.get("symbol") or "UNKNOWN"
            positions.append({
                "token": symbol,
                "chain_id": t.get("chain_id", 1),
                "usd": _try_float(t.get("usd_value") or t.get("amount_usd"), 0.0),
                "apy": _try_float(t.get("apy"), 0.0),
                "sentinel": _try_int(t.get("sentinel"), 50),
            })
    return positions


def _resolve_chain_id(name: str) -> int:
    mapping = {
        "ethereum": 1, "eth": 1,
        "arbitrum": 42161,
        "polygon": 137,
        "bsc": 56,
        "base": 8453,
        "optimism": 10,
        "avalanche": 43114,
        "solana": 101,
    }
    return mapping.get(name.lower(), 1)


def _try_float(v, default):
    try:
        return float(v or default)
    except (TypeError, ValueError):
        return default


def _try_int(v, default):
    try:
        return int(v or default)
    except (TypeError, ValueError):
        return default
