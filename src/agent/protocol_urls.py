"""Map DefiLlama protocol slugs to the actual protocol app URL.

DefiLlama's `defillama.com/protocol/<slug>` is internal browsing on DefiLlama,
not a place where users execute. Pool cards in chat should link to the real
protocol app so the user can deposit/withdraw directly.

Falls back to the project_url passed by DefiLlama (the protocol's `url` field
in /protocols), or to defillama.com/protocol/<slug> if nothing else is known.
"""

from __future__ import annotations

# Curated mapping for the protocols we surface most often. Slugs match
# DefiLlama's `project` / `protocol_slug`. Values are the protocol's own
# user-facing app URL (NOT a marketing site), so deposit flows just work.
PROTOCOL_APP_URL: dict[str, str] = {
    # EVM AMMs / aggregators
    "uniswap-v2": "https://app.uniswap.org/swap",
    "uniswap-v3": "https://app.uniswap.org/swap",
    "uniswap-v4": "https://app.uniswap.org/swap",
    "sushiswap": "https://www.sushi.com/swap",
    "pancakeswap": "https://pancakeswap.finance/swap",
    "pancakeswap-amm": "https://pancakeswap.finance/swap",
    "pancakeswap-amm-v3": "https://pancakeswap.finance/swap",
    "pancakeswap-stableswap": "https://pancakeswap.finance/swap",
    "curve-dex": "https://curve.fi",
    "curve": "https://curve.fi",
    "balancer": "https://app.balancer.fi",
    "balancer-v2": "https://app.balancer.fi",
    "balancer-v3": "https://app.balancer.fi",
    "aerodrome": "https://aerodrome.finance",
    "aerodrome-v1": "https://aerodrome.finance",
    "aerodrome-slipstream": "https://aerodrome.finance/liquidity",
    "velodrome": "https://velodrome.finance",
    "velodrome-v2": "https://velodrome.finance",
    "ramses-v2": "https://app.ramses.exchange",
    "camelot-v3": "https://app.camelot.exchange",
    "thena": "https://www.thena.fi",
    # EVM lending
    "aave-v2": "https://app.aave.com",
    "aave-v3": "https://app.aave.com",
    "compound": "https://app.compound.finance",
    "compound-v3": "https://app.compound.finance",
    "morpho": "https://app.morpho.org",
    "morpho-blue": "https://app.morpho.org",
    "spark": "https://app.spark.fi",
    "moonwell": "https://moonwell.fi",
    "venus": "https://app.venus.io",
    "radiant-v2": "https://app.radiant.capital",
    # Yield
    "yearn-finance": "https://yearn.fi/v3",
    "convex-finance": "https://www.convexfinance.com",
    "pendle": "https://app.pendle.finance",
    "stargate-v2": "https://stargate.finance",
    # LSTs & staking
    "lido": "https://stake.lido.fi",
    "rocket-pool": "https://stake.rocketpool.net",
    "ether.fi-stake": "https://app.ether.fi",
    "ether.fi-liquid": "https://app.ether.fi",
    "ether-fi": "https://app.ether.fi",
    "frax-ether": "https://frax.com/staking",
    "swell-network": "https://app.swellnetwork.io",
    "lista-dao": "https://lista.org/liquid-staking",
    "stader": "https://www.staderlabs.com",
    # Solana
    "raydium-amm": "https://raydium.io/liquidity-pools",
    "raydium-clmm": "https://raydium.io/clmm-pools",
    "raydium": "https://raydium.io",
    "orca": "https://www.orca.so/pools",
    "orca-whirlpools": "https://www.orca.so/pools",
    "meteora": "https://app.meteora.ag",
    "meteora-dlmm": "https://app.meteora.ag/dlmm",
    "kamino": "https://app.kamino.finance",
    "kamino-lend": "https://app.kamino.finance/lending",
    "kamino-liquidity": "https://app.kamino.finance/liquidity",
    "marinade-finance": "https://app.marinade.finance",
    "marinade-native": "https://app.marinade.finance",
    "marinade": "https://app.marinade.finance",
    "jito": "https://www.jito.network/staking",
    "jito-liquid-staking": "https://www.jito.network/staking",
    "sanctum": "https://app.sanctum.so",
    "drift-trade": "https://app.drift.trade",
    "drift": "https://app.drift.trade",
    "lulo": "https://lulo.fi",
    "save": "https://save.finance",
    "lifinity": "https://lifinity.io",
    "solend": "https://solend.fi/dashboard",
    # New / niche but seen in pool listings
    "zeebu": "https://zeebu.com",
    "steer-protocol": "https://app.steer.finance",
    "blackhole-clmm": "https://www.blackhole.dev",
    "supernova-cl": "https://supernovaprotocol.com",
}


def protocol_app_url(slug: str | None, *, project_url: str | None = None) -> str | None:
    """Best-effort URL pointing to the protocol's own app for the given slug.

    Resolution order:
      1. Curated mapping (most accurate, points to deposit/swap flow).
      2. project_url passed in by caller (DefiLlama's `url` field, often the
         marketing homepage — still better than DefiLlama's internal page).
      3. None — caller decides on a final fallback.
    """
    if slug:
        key = slug.strip().lower()
        if key in PROTOCOL_APP_URL:
            return PROTOCOL_APP_URL[key]
        # Try common stripped variants — drop trailing -v1/-v2/-v3/-v4 etc.
        head = key.rsplit("-v", 1)[0] if "-v" in key else key
        if head in PROTOCOL_APP_URL:
            return PROTOCOL_APP_URL[head]
    if project_url and isinstance(project_url, str) and project_url.startswith(("http://", "https://")):
        return project_url
    return None
