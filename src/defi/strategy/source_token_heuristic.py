"""Spec §6d source-token smart-heuristic.

When the user says "deposit X USDC into Y pool with my USDT", the planner has
three paths:
  (A) silent-split + exposure_disclosure card
  (B) suggest a USDT-native pool with high APR + dominant USDT share (preferable
      because no swap needed, fewer fees, and matches user's apparent intent
      of staying in USDT)
  (C) hard-block if no viable route

This module picks (B) when a USDT-native pool exists with APR >= 20% AND >=50% of
TVL is in USDT. Falls through to (A) otherwise.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


SMART_HEURISTIC_MIN_APR = Decimal("0.20")  # 20%
SMART_HEURISTIC_MIN_TOKEN_SHARE = Decimal("0.50")  # 50% of TVL


@dataclass(frozen=True)
class SourceTokenCandidate:
    pool_address: str
    protocol: str
    chain: str
    pair_symbols: tuple[str, str]  # e.g. ("USDT", "DAI")
    apr_30d: Decimal
    tvl_usd: Decimal
    source_token_share: Decimal  # fraction of TVL in the source_token


def is_smart_heuristic_eligible(c: SourceTokenCandidate) -> bool:
    """True iff candidate meets §6d (B)-path criteria."""
    return c.apr_30d >= SMART_HEURISTIC_MIN_APR and c.source_token_share >= SMART_HEURISTIC_MIN_TOKEN_SHARE


def pick_smart_heuristic_alternative(
    source_token: str,
    candidates: list[SourceTokenCandidate],
) -> Optional[SourceTokenCandidate]:
    """Return the highest-APR §6d-eligible candidate, or None."""
    eligible = [c for c in candidates if is_smart_heuristic_eligible(c)]
    if not eligible:
        return None
    # Highest APR wins. Tie-breaker: largest source_token_share, then TVL.
    return max(eligible, key=lambda c: (c.apr_30d, c.source_token_share, c.tvl_usd))


def build_redirect_recommendation_card(
    source_token: str,
    original_pool: str,
    alternative: SourceTokenCandidate,
) -> dict:
    """Card emitted to surface (B)-path to user before signing."""
    return {
        "card_type": "source_token_redirect",
        "source_token": source_token,
        "original_pool": original_pool,
        "alternative_pool": {
            "address": alternative.pool_address,
            "protocol": alternative.protocol,
            "chain": alternative.chain,
            "pair": "/".join(alternative.pair_symbols),
            "apr_30d": str(alternative.apr_30d),
            "tvl_usd": str(alternative.tvl_usd),
            "source_token_share": str(alternative.source_token_share),
        },
        "recommendation": (
            f"Your {source_token} could earn {alternative.apr_30d * 100:.1f}% in a native "
            f"{alternative.pair_symbols[0]}/{alternative.pair_symbols[1]} pool on "
            f"{alternative.protocol} without converting. Pick this alternative or proceed "
            f"with the silent-split into the original pool."
        ),
        "user_choice": ["use_alternative", "proceed_with_split", "cancel"],
    }
