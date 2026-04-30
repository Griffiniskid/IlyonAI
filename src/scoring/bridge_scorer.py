from __future__ import annotations

from typing import Any

from src.api.schemas.agent import SentinelBlock, ShieldBlock
from src.scoring.normalizer import pool_candidate_from_mapping
from src.scoring.rubric import sentinel_block_from_candidate
from src.scoring.shield_gate import shield_for_transaction


CHAIN_LABELS = {
    1: "Ethereum",
    10: "Optimism",
    56: "BSC",
    137: "Polygon",
    42161: "Arbitrum",
    8453: "Base",
    7565164: "Solana",
}


def score_bridge_mapping(route: dict[str, Any]) -> tuple[SentinelBlock, ShieldBlock]:
    token = str(route.get("token_out") or route.get("token_in") or route.get("token") or "USDC")
    dst_chain_id = int(route.get("dst_chain_id") or route.get("target_chain_id") or route.get("chain_id") or 1)
    chain = CHAIN_LABELS.get(dst_chain_id, str(dst_chain_id))
    candidate = pool_candidate_from_mapping(
        {
            "project": route.get("destination_protocol") or "stargate",
            "symbol": token,
            "chain": chain,
            "tvlUsd": route.get("destination_tvl_usd") or route.get("tvlUsd") or 300_000_000,
            "apy": route.get("destination_apy") or 3.0,
            "stablecoin": token.upper() in {"USDC", "USDT", "DAI"},
            "ilRisk": "no",
        }
    )
    sentinel = sentinel_block_from_candidate(candidate)
    shield = shield_for_transaction({**route, "spender": route.get("spender") or route.get("router") or "deBridge"})
    if "Cross-chain route" not in shield.reasons:
        shield.reasons.append("Cross-chain route")
    if shield.verdict == "SAFE":
        shield.verdict = "CAUTION"
        shield.grade = "B"
    return sentinel, shield
