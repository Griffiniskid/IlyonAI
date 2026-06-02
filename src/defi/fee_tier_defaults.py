"""Pair-category fee-tier default resolver (V7-017).

When a user does not specify a fee tier for a Uniswap V3 / Slipstream / similar
concentrated-liquidity pool, choose a sensible default based on the *category*
of the pair (stable / blue-chip / exotic).

Spec §3 mapping
---------------
- stable/stable           -> 1 bp   (fee_tier = 100)
- stable/blue (ETH/BTC)   -> 5 bp   (fee_tier = 500)
- blue/blue               -> 30 bp  (fee_tier = 3000)
- exotic (everything else)-> 100 bp (fee_tier = 10000)

The resolver is symbol-driven and case-insensitive. Bridge-suffixed variants
(``USDC.e``, ``USDT.e``) are treated as their canonical stable counterparts.
"""

from __future__ import annotations

from typing import Literal

# --------------------------------------------------------------------------- #
# Token classification sets                                                   #
# --------------------------------------------------------------------------- #

# Major USD-denominated stablecoins + native-DAI variant (xDAI) +
# common bridge-suffix variants (USDC.e on Avalanche/Arbitrum etc.).
STABLE_TOKENS: frozenset[str] = frozenset(
    {
        "USDC",
        "USDT",
        "DAI",
        "FRAX",
        "USDE",
        "USDS",
        "PYUSD",
        "USDP",
        "TUSD",
        "BUSD",
        "LUSD",
        "GHO",
        "CRVUSD",
        "FDUSD",
        "USDB",
        "USDX",
        "XDAI",
        "USDC.E",
        "USDT.E",
    }
)

# Blue-chip "money" assets: ETH + BTC (and their major liquid-staking /
# wrapped variants). These pair *with each other* at the 30 bp tier and
# pair against stables at the 5 bp tier.
BLUE_TOKENS: frozenset[str] = frozenset(
    {
        "WETH",
        "ETH",
        "WBTC",
        "BTC",
        "CBBTC",
        "TBTC",
        "LBTC",
        "STETH",
        "WSTETH",
        "RETH",
        "WEETH",
    }
)

PairCategory = Literal["stable_stable", "stable_blue", "blue_blue", "exotic"]


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def _normalize(symbol: str) -> str:
    """Upper-case and strip whitespace for set membership checks."""
    return (symbol or "").strip().upper()


def categorize_pair(t0: str, t1: str) -> PairCategory:
    """Classify the (t0, t1) symbol pair into one of four categories.

    Comparison is case-insensitive. Symbol order does not matter.
    """
    a = _normalize(t0)
    b = _normalize(t1)

    a_stable = a in STABLE_TOKENS
    b_stable = b in STABLE_TOKENS
    a_blue = a in BLUE_TOKENS
    b_blue = b in BLUE_TOKENS

    if a_stable and b_stable:
        return "stable_stable"
    if (a_stable and b_blue) or (a_blue and b_stable):
        return "stable_blue"
    if a_blue and b_blue:
        return "blue_blue"
    return "exotic"


def default_fee_tier(t0: str, t1: str) -> int:
    """Return the default Uniswap-V3-style fee tier (in hundredths of a bp).

    100   -> 0.01% (stable/stable)
    500   -> 0.05% (stable/blue)
    3000  -> 0.30% (blue/blue)
    10000 -> 1.00% (exotic)
    """
    category = categorize_pair(t0, t1)
    if category == "stable_stable":
        return 100
    if category == "stable_blue":
        return 500
    if category == "blue_blue":
        return 3000
    return 10000


# Canonical spec name (§3.2). Identical behaviour to default_fee_tier — kept as
# a named alias so callers can use the spec's wording.
default_fee_tier_for_pair = default_fee_tier


__all__ = [
    "STABLE_TOKENS",
    "BLUE_TOKENS",
    "PairCategory",
    "categorize_pair",
    "default_fee_tier",
    "default_fee_tier_for_pair",
]
