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


# --- Direct pool deeplink resolution ---------------------------------------
#
# When the agent surfaces a specific DefiLlama pool, we want to link the user
# to the EXACT pool on the protocol's own app, not the protocol home page.
# `pool_protocol_url` accepts the metadata DefiLlama already gives us and
# returns the best per-pool URL it can build. Falls through to the protocol
# home (via `protocol_app_url`) if a per-pool deeplink can't be constructed.

from urllib.parse import quote_plus

# DefiLlama chain string → Aave V3 market name slug
_AAVE_MARKET = {
    "ethereum": "proto_mainnet_v3",
    "arbitrum": "proto_arbitrum_v3",
    "optimism": "proto_optimism_v3",
    "polygon": "proto_polygon_v3",
    "base": "proto_base_v3",
    "avalanche": "proto_avalanche_v3",
    "bsc": "proto_bnb_v3",
    "gnosis": "proto_gnosis_v3",
    "metis": "proto_metis_v3",
    "scroll": "proto_scroll_v3",
    "linea": "proto_linea_v3",
    "zksync era": "proto_zksync_v3",
    "fantom": "proto_fantom_v3",
}

# Compound V3 chain → URL path slug
_COMPOUND_CHAIN = {
    "ethereum": "mainnet",
    "arbitrum": "arb",
    "base": "basemainnet",
    "polygon": "polygon",
    "optimism": "optimism",
    "scroll": "scroll",
}

# Uniswap chain slug
_UNI_CHAIN = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "polygon": "polygon",
    "base": "base",
    "bsc": "bnb",
    "avalanche": "avalanche",
    "celo": "celo",
    "zksync era": "zksync",
}

# Curve chain slug
_CURVE_CHAIN = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "polygon": "polygon",
    "base": "base",
    "fantom": "fantom",
    "avalanche": "avalanche",
    "gnosis": "xdai",
    "bsc": "bsc",
    "fraxtal": "fraxtal",
}

# Balancer chain slug
_BAL_CHAIN = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "polygon": "polygon",
    "base": "base",
    "gnosis": "gnosis",
    "avalanche": "avalanche",
    "zksync era": "zkevm",
}

# Yearn V3 chain id (numeric)
_YEARN_CHAIN_ID = {
    "ethereum": "1",
    "arbitrum": "42161",
    "optimism": "10",
    "polygon": "137",
    "base": "8453",
    "fantom": "250",
}


def _chain_key(chain: str | None) -> str:
    return (chain or "").strip().lower()


def _project_key(project: str | None) -> str:
    return (project or "").strip().lower()


def _first_underlying(underlying_tokens) -> str | None:
    """Returns the first non-empty underlying token address."""
    if not underlying_tokens:
        return None
    if isinstance(underlying_tokens, str):
        s = underlying_tokens.strip()
        return s or None
    try:
        for raw in underlying_tokens:
            if not raw:
                continue
            s = str(raw).strip()
            if s:
                return s
    except TypeError:
        return None
    return None


def pool_protocol_url(
    *,
    chain: str | None,
    project: str | None,
    pool_address: str | None = None,
    underlying_tokens=None,
    pool_symbol: str | None = None,
    project_url: str | None = None,
) -> str:
    """Direct per-pool URL on the protocol's own app.

    Always returns a URL — falls back to `protocol_app_url` then to a generic
    DefiLlama page as a last resort.
    """
    proj = _project_key(project)
    ch = _chain_key(chain)
    pa = (pool_address or "").strip()
    sym = (pool_symbol or "").strip()
    first_under = _first_underlying(underlying_tokens)

    # --- EVM lending ---
    if proj in {"aave-v3", "aave-v2", "aave"}:
        market = _AAVE_MARKET.get(ch, "proto_mainnet_v3")
        if first_under:
            return (
                "https://app.aave.com/reserve-overview/"
                f"?underlyingAsset={first_under.lower()}&marketName={market}"
            )
        return "https://app.aave.com/markets/"

    if proj in {"compound-v3", "compound"}:
        slug = _COMPOUND_CHAIN.get(ch, "mainnet")
        return f"https://app.compound.finance/markets/v3-{slug}"

    if proj in {"morpho-blue", "morpho", "morpho-aave-v3", "morpho-aave-v2", "morpho-compound"}:
        if pa:
            return f"https://app.morpho.org/market?id={pa}&network={ch or 'mainnet'}"
        return "https://app.morpho.org/"

    if proj in {"spark", "sparklend"}:
        return "https://app.spark.fi/markets/"

    if proj in {"venus", "venus-core-pool", "venus-isolated-pools"}:
        if first_under:
            return f"https://app.venus.io/#/core-pool/market/{first_under}"
        return "https://app.venus.io/#/core-pool/markets"

    if proj in {"radiant-v2", "radiant"}:
        return "https://app.radiant.capital/"

    if proj in {"moonwell"}:
        return f"https://moonwell.fi/markets/{ch or 'base'}"

    # --- EVM AMMs / concentrated liquidity ---
    if proj.startswith("uniswap"):
        u_ch = _UNI_CHAIN.get(ch, ch or "ethereum")
        if pa:
            return f"https://app.uniswap.org/explore/pools/{u_ch}/{pa}"
        if sym:
            return f"https://app.uniswap.org/explore/pools/{u_ch}?search={quote_plus(sym)}"
        return f"https://app.uniswap.org/explore/pools/{u_ch}"

    if proj in {"curve-dex", "curve", "curve-llamalend"}:
        c_ch = _CURVE_CHAIN.get(ch, "ethereum")
        if sym:
            return f"https://curve.fi/#/{c_ch}/pools?search={quote_plus(sym)}"
        return f"https://curve.fi/#/{c_ch}/pools"

    if proj.startswith("balancer"):
        b_ch = _BAL_CHAIN.get(ch, "ethereum")
        if pa:
            return f"https://balancer.fi/pools/{b_ch}/v2/{pa}"
        if sym:
            return f"https://balancer.fi/pools?poolTypes=&networks={b_ch}&textSearch={quote_plus(sym)}"
        return f"https://balancer.fi/pools?networks={b_ch}"

    if proj.startswith("aerodrome"):
        if pa:
            return f"https://aerodrome.finance/liquidity?query={pa}"
        if sym:
            return f"https://aerodrome.finance/liquidity?query={quote_plus(sym)}"
        return "https://aerodrome.finance/liquidity"

    if proj.startswith("velodrome"):
        if pa:
            return f"https://velodrome.finance/liquidity?query={pa}"
        if sym:
            return f"https://velodrome.finance/liquidity?query={quote_plus(sym)}"
        return "https://velodrome.finance/liquidity"

    if proj.startswith("pancakeswap"):
        # PancakeSwap V3 LP UI
        if pa:
            return f"https://pancakeswap.finance/info/v3/pools/{pa}"
        return "https://pancakeswap.finance/liquidity"

    if proj in {"sushiswap", "sushiswap-v3"}:
        return "https://www.sushi.com/pool"

    if proj in {"camelot-v3", "camelot"}:
        return "https://app.camelot.exchange/pools"

    if proj in {"ramses-v2", "ramses"}:
        return "https://app.ramses.exchange/liquidity"

    if proj in {"thena", "thena-v1", "thena-fusion"}:
        return "https://www.thena.fi/fusion"

    # --- EVM yield / vaults ---
    if proj in {"pendle", "pendle-v2"}:
        if pa:
            return f"https://app.pendle.finance/trade/markets/{pa}"
        return "https://app.pendle.finance/trade/markets"

    if proj.startswith("yearn"):
        chain_id = _YEARN_CHAIN_ID.get(ch, "1")
        if pa:
            return f"https://yearn.fi/v3/{chain_id}/{pa}"
        return f"https://yearn.fi/v3?chains={chain_id}"

    if proj.startswith("convex"):
        return "https://www.convexfinance.com/stake"

    if proj.startswith("beefy"):
        if pa:
            return f"https://app.beefy.com/vault/{pa}"
        return "https://app.beefy.com/"

    # --- LSTs / staking ---
    if proj in {"lido", "lido-stake"}:
        return "https://stake.lido.fi/"
    if proj in {"rocket-pool", "rocketpool"}:
        return "https://stake.rocketpool.net/"
    if proj in {"ether.fi-stake", "ether-fi", "etherfi", "ether.fi-liquid"}:
        return "https://app.ether.fi/"
    if proj in {"frax-ether", "frxeth"}:
        return "https://frax.com/frax-ether"
    if proj in {"swell-network", "swell"}:
        return "https://app.swellnetwork.io/stake"
    if proj in {"stader"}:
        return "https://www.staderlabs.com/"

    # --- Solana ---
    if proj in {"raydium-amm", "raydium-amm-v3", "raydium-cp"}:
        if pa:
            return f"https://raydium.io/liquidity/?ammId={pa}"
        if sym:
            return f"https://raydium.io/liquidity-pools/?search={quote_plus(sym)}"
        return "https://raydium.io/liquidity-pools/"

    if proj in {"raydium-clmm"}:
        if pa:
            return f"https://raydium.io/clmm/?pool_id={pa}"
        if sym:
            return f"https://raydium.io/clmm-pools/?search={quote_plus(sym)}"
        return "https://raydium.io/clmm-pools/"

    if proj in {"orca", "orca-dex", "orca-whirlpools", "orca-clmm"}:
        if pa:
            return f"https://www.orca.so/pools?tokens={pa}"
        if sym:
            return f"https://www.orca.so/pools?search={quote_plus(sym)}"
        return "https://www.orca.so/pools"

    if proj in {"meteora-dlmm"}:
        if pa:
            return f"https://app.meteora.ag/dlmm/{pa}"
        return "https://app.meteora.ag/dlmm"

    if proj in {"meteora-amm", "meteora-vault", "meteora"}:
        if pa:
            return f"https://app.meteora.ag/pools/{pa}"
        return "https://app.meteora.ag/"

    if proj in {"kamino-lend", "kamino-finance", "kamino"}:
        return "https://app.kamino.finance/lending"
    if proj in {"kamino-liquidity", "kamino-vault"}:
        return "https://app.kamino.finance/liquidity"

    if proj in {"marinade-finance", "marinade-native", "marinade", "marinade-liquid-staking"}:
        return "https://app.marinade.finance/"
    if proj in {"jito", "jito-liquid-staking"}:
        return "https://www.jito.network/staking/"
    if proj in {"sanctum", "sanctum-infinity", "sanctum-liquid-staking"}:
        return "https://app.sanctum.so/"
    if proj in {"drift", "drift-perps", "drift-spot", "drift-staked-sol", "drift-trade"}:
        if sym:
            return f"https://app.drift.trade/earn?market={quote_plus(sym)}"
        return "https://app.drift.trade/earn"
    if proj in {"lulo", "lulo-finance"}:
        return "https://lulo.fi/"
    if proj in {"save", "save-finance", "solend"}:
        return "https://save.finance/dashboard"
    if proj in {"lifinity", "lifinity-v2"}:
        return "https://lifinity.io/pools"

    # --- Generic fallback chain ---
    home = protocol_app_url(project, project_url=project_url)
    if home:
        return home
    if project:
        return f"https://defillama.com/protocol/{quote_plus(project.lower())}"
    return "https://defillama.com/yields"


# Protocols where action="stake" is a single-asset liquid-staking deposit
# (no pool counterparty needed) — these CAN still execute through wallet.
# Everything else under action="stake" goes through link-only path because
# it requires LP / pool counterparties.
LST_STAKE_PROTOCOLS = frozenset({
    "lido", "lido-stake",
    "rocket-pool", "rocketpool",
    "ether.fi", "ether.fi-stake", "ether-fi", "etherfi", "ether.fi-liquid",
    "frax", "frax-ether", "frx-ether", "frxeth", "sfrxeth",
    "swell-network", "swell",
    "lista-dao",
    "stader",
    "marinade-finance", "marinade-native", "marinade", "marinade-liquid-staking",
    "jito", "jito-liquid-staking",
    "sanctum", "sanctum-infinity", "sanctum-liquid-staking",
})


# Pool-deposit-style actions. When the action falls in this set, agent should
# emit a pool_link card instead of an execution plan.
POOL_LINK_ACTIONS = frozenset({
    "supply", "deposit", "deposit_lp", "lend", "provide_liquidity", "add_liquidity",
})

# Protocols whose EVM supply / lend / deposit_lp path is known-good.
# After plan v3 (Phase A), Enso routes the calldata for every entry below:
# Aave V3, Compound V3, Curve, Balancer, Yearn, Morpho, Spark, Sky, Lido,
# RocketPool, EtherFi, Frax, Pendle, Stargate, Stader, Moonwell, GMX,
# Velodrome, Aerodrome (non-CL).
SUPPLY_EXEC_PROTOCOLS = frozenset({
    "aave-v3", "aave-v2", "aave", "aave-v3-prime", "aavev3",
    "compound-v3", "compound-v2", "compound", "compoundv3",
    "yearn", "yearn-finance", "yearn-v3",
    "morpho", "morpho-blue", "metamorpho",
    "spark", "spark-protocol", "spark-lending",
    "sky", "sky-lending", "makerdao",
    "fluid", "fluid-lending",
    "moonwell",
    "stargate",
    "origin", "origin-ether",
    "ethena", "pendle",
})

# Enso-backed protocols where deposit_lp / supply / lend all route through
# the Enso shortcut adapter. These bypass the pool_link fallback because the
# adapter returns real calldata (verified live for Aave V3, Compound V3,
# Curve, Balancer, Yearn, Morpho, Spark on Eth/Base/Arb/Polygon/Optimism).
EVM_ENSO_EXEC_PROTOCOLS = frozenset(
    SUPPLY_EXEC_PROTOCOLS
    | {
        "curve", "curve-dex", "curve-finance", "curve-stable", "curve-lending",
        "balancer", "balancer-v2", "balancer-v3",
        "lido", "rocket-pool", "rocketpool",
        "ether.fi", "ether-fi", "etherfi", "weeth",
        "frax", "frax-ether", "frx-ether", "sfrxeth",
        "stader",
        "gmx",
        "velodrome", "aerodrome",
    }
)

# EVM stable LP protocols where single-sided add_liquidity executes natively
# (Curve / Balancer single-asset join). Bypasses the link-only fallback for
# action=add_liquidity / deposit_lp / provide_liquidity.
STABLE_LP_EXEC_PROTOCOLS = frozenset({
    "curve", "curve-dex", "curve-finance", "curve-stable",
    "balancer", "balancer-v2", "balancer-v3",
})

# V2 LP protocols where dual-token addLiquidity executes natively. Requires
# the user to provide BOTH sides (parser captures "X TOKEN_A and Y TOKEN_B").
# Single-sided V2 zap (swap + add) is a follow-up phase.
V2_LP_EXEC_PROTOCOLS = frozenset({
    "uniswap-v2", "uniswap", "univ2", "uniswap2",
    "sushiswap", "sushi", "sushiswap-v2",
    "pancakeswap-v2", "pancakeswap", "pancake-v2", "pancake", "pancakeswap-amm",
    "quickswap",
    "camelot",
    "velodrome-v1", "velodrome",
    "baseswap",
    "trader-joe-v1", "trader-joe", "traderjoe",
})

# Concentrated-liquidity protocols where Enso silently routes to aUSDC or
# fails — always redirect to the protocol app until Phase 4 range UI ships.
V3_PROTOCOLS = frozenset({
    "uniswap-v3", "uniswap-v4",
    "pancakeswap-v3", "pancake-v3",
    "sushiswap-v3", "sushi-v3",
    "aerodrome-slipstream", "aerodrome-cl",
    "kim",
    "thena-v3", "thena-fusion",
    "ramses-v2", "ramses-cl",
    "trader-joe-v2",
})


_V3_HINTS = ("v3", "v4", "clmm", "slipstream", "concentrated", "kim", "thena-fusion", "fusion")
_STABLE_HINTS = ("curve", "balancer", "saddle", "mim-swap", "convex")
_VAULT_HINTS = ("yearn", "morpho", "spark", "beefy", "gamma", "arrakis", "steer-protocol", "ichi", "aave")


def classify_pool_kind(*, protocol: str | None, pool_symbol: str | None = None, pool_id: str | None = None) -> str:
    """Return 'v3' | 'stable' | 'vault' | 'v2' for the pool_link / pool_deposit_v3
    cards. Routes through the explicit `pool_types.lookup_pool_type` registry
    so new protocols land in the right bucket without ad-hoc substrings.
    """
    from src.agent.pool_types import kind_for_card
    primary = kind_for_card(protocol)
    if primary != "v2":
        return primary
    # When the protocol slug is generic ("uniswap" without a version), fall
    # back to the legacy substring heuristic over (protocol, symbol, pool_id)
    # blob so we don't lose V3 / stable / vault detection for ambiguous slugs.
    p = (protocol or "").lower()
    sym = (pool_symbol or "").lower()
    pid = (pool_id or "").lower()
    blob = f"{p} {sym} {pid}"
    if any(h in blob for h in _V3_HINTS):
        return "v3"
    if any(h in blob for h in _STABLE_HINTS):
        return "stable"
    if any(h in blob for h in _VAULT_HINTS):
        return "vault"
    return "v2"


def is_pool_link_action(*, action: str | None, protocol: str | None, chain: str | None = None) -> bool:
    """True when this (action, protocol, chain) tuple should be link-only.

    With-exec branch rules:
      - V3 / CLMM deposit on EVM → always link-only (silent mis-routing bug).
      - Solana → never link-only at this layer (sidecar adapters handle the
        prep-swap and sim-gate themselves; the runtime trusts their output).
      - EVM deposit_lp / provide_liquidity / add_liquidity → link-only by
        default until the Phase 2 V2 zap composer lands.
      - EVM supply / deposit / lend → link-only UNLESS protocol is in the
        SUPPLY_EXEC_PROTOCOLS whitelist (Aave / Compound work today).
      - stake → link-only UNLESS protocol is a recognized LST.
    """
    a = (action or "").strip().lower()
    p = (protocol or "").strip().lower()
    c = (chain or "").strip().lower()

    # Solana: let sidecar adapters drive the flow (pair-aware prep-swap + sim).
    if c in ("solana", "sol"):
        return False

    # V3 always redirects on EVM until the V3 NFT-position adapter ships.
    if a in {"deposit_lp", "provide_liquidity", "add_liquidity"} and p in V3_PROTOCOLS:
        return True

    # Enso-backed EVM protocols (covers Curve / Balancer / Yearn / Morpho /
    # Spark / Lido / RocketPool / EtherFi / Stargate / Stader / GMX /
    # Velodrome / Aerodrome and the SUPPLY_EXEC_PROTOCOLS set).
    if a in {"deposit_lp", "provide_liquidity", "add_liquidity", "supply", "deposit", "lend"} \
            and p in EVM_ENSO_EXEC_PROTOCOLS:
        return False

    # V2 dual-token addLiquidity executes natively (Phase 7 baseline). Note: the
    # adapter requires BOTH amounts in extra; runtime supplies them when the
    # parser matches the "X TOKEN_A and Y TOKEN_B" phrasing. If only one amount
    # is present, build_yield_execution_plan emits a structured blocker rather
    # than a pool_link redirect, which keeps the matrix coverage explicit.
    if a in {"deposit_lp", "provide_liquidity", "add_liquidity"} and p in V2_LP_EXEC_PROTOCOLS:
        return False

    # Generic deposit_lp / add_liquidity on EVM — redirect until V3 NFT lands.
    if a in {"deposit_lp", "provide_liquidity", "add_liquidity"}:
        return True

    # EVM supply / deposit / lend — let known-good protocols through.
    if a in {"supply", "deposit", "lend"}:
        if p in SUPPLY_EXEC_PROTOCOLS:
            return False
        return True

    # Stake — LSTs only.
    if a == "stake" and p not in LST_STAKE_PROTOCOLS:
        return True

    return False
