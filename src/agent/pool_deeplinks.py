"""Build a deep link to a SPECIFIC pool on the correct protocol.

The "Open pool" button must take the user straight to *that pool* on the
protocol's own app — never the protocol homepage. Resolution order per
protocol:
  1. protocol-native exact-pool URL by pool address (best — lands on the
     add-liquidity / pool page)
  2. protocol-native add-liquidity URL by the pair's two token addresses
     (when we have the tokens but not the pool address)
  3. DexScreener exact pair page by address (always exact for any pair)
  4. DefiLlama exact pool page by UUID (always the specific pool)
"""
from __future__ import annotations

_DEFILLAMA_POOL = "https://defillama.com/yields/pool/{uuid}"

# Aave V3 market name per chain (for the reserve-overview deep link).
_AAVE_MARKET = {
    "ethereum": "proto_mainnet_v3", "base": "proto_base_v3",
    "arbitrum": "proto_arbitrum_v3", "optimism": "proto_optimism_v3",
    "polygon": "proto_polygon_v3", "avalanche": "proto_avalanche_v3",
    "bsc": "proto_bnb_v3", "gnosis": "proto_gnosis_v3", "scroll": "proto_scroll_v3",
}
# Uniswap interface uses "bnb" for BSC; everything else matches.
_UNI_CHAIN = {"bsc": "bnb"}
# EVM chain → numeric chain id (Sushi's pool URL is /pool/{chainId}%3A{addr}).
_CHAIN_ID = {
    "ethereum": 1, "optimism": 10, "bsc": 56, "polygon": 137, "base": 8453,
    "arbitrum": 42161, "avalanche": 43114, "gnosis": 100, "scroll": 534352,
}


def _n(value: str | None) -> str:
    return (value or "").lower().strip()


def _evm_addrs(tokens: list[str] | None) -> list[str]:
    return [t for t in (tokens or []) if isinstance(t, str) and t.lower().startswith("0x") and len(t) == 42]


def _fallback(
    *,
    protocol: str | None,
    chain: str | None,
    pool_id: str | None,
    pool_address: str | None,
    symbol: str | None,
    underlying_tokens: list[str] | None,
) -> str:
    """Best link when no protocol-native EXACT pool URL could be built. Send the
    user to the PROTOCOL'S OWN APP first (never an aggregator if we can avoid
    it); DefiLlama is the strict last resort. Order:
      1. protocol app URL (the protocol's own site)
      2. DexScreener exact pair (by address) — only if we have one
      3. DefiLlama exact pool (by UUID) — last resort
      4. pool_protocol_url (always returns something usable)."""
    from src.agent.protocol_urls import protocol_app_url, pool_protocol_url
    c = _n(chain)
    addr = pool_address if (isinstance(pool_address, str) and pool_address) else None
    app = protocol_app_url(_n(protocol))
    if app:
        return app
    if addr and c:
        return f"https://dexscreener.com/{c}/{addr}"
    if pool_id and "-" in str(pool_id):
        return _DEFILLAMA_POOL.format(uuid=pool_id)
    return pool_protocol_url(
        chain=chain, project=protocol, pool_address=pool_address,
        underlying_tokens=underlying_tokens, pool_symbol=symbol,
    )


def pool_deeplink(
    *,
    protocol: str | None,
    chain: str | None,
    pool_id: str | None,
    pool_address: str | None = None,
    symbol: str | None = None,
    underlying_tokens: list[str] | None = None,
) -> str:
    p = _n(protocol)
    c = _n(chain)
    addr = pool_address if (isinstance(pool_address, str) and pool_address) else None
    mints = [m for m in (underlying_tokens or []) if m]
    evm_toks = _evm_addrs(underlying_tokens)

    _fb = lambda: _fallback(  # noqa: E731 — local shorthand for the shared fallback
        protocol=protocol, chain=chain, pool_id=pool_id,
        pool_address=pool_address, symbol=symbol, underlying_tokens=underlying_tokens,
    )

    # When we have the pool's ADDRESS we build the protocol-native EXACT pool
    # page below (curve/uniswap/aave/…) — far better than the bare homepage.
    # Only when no exact form can be built do we fall back to the protocol app
    # homepage (and DefiLlama strictly last). The earlier blanket "return the
    # homepage first" short-circuit hid the exact address links AND dropped
    # unmapped protocols (Fluid) onto DefiLlama.

    # ─── Solana ───────────────────────────────────────────────────────────
    if c in {"solana", "sol"}:
        if "raydium" in p:
            if addr:
                return f"https://raydium.io/liquidity/?pool_id={addr}"
            if len(mints) >= 2:
                return f"https://raydium.io/liquidity/add/?inputMint={mints[0]}&outputMint={mints[1]}"
        elif "orca" in p and addr:
            return f"https://www.orca.so/pools/{addr}"
        elif "meteora" in p and addr:
            return f"https://app.meteora.ag/dlmm/{addr}"
        elif "marinade" in p:
            return "https://marinade.finance/app/staking/"
        elif "jito" in p:
            return "https://www.jito.network/staking/"
        elif "kamino" in p and addr:
            return f"https://app.kamino.finance/lending/reserve/{addr}"
        return _fb()

    # ─── EVM lending (exact reserve page, not homepage) ───────────────────
    if "aave" in p:
        market = _AAVE_MARKET.get(c, "proto_mainnet_v3")
        if evm_toks:
            return f"https://app.aave.com/reserve-overview/?underlyingAsset={evm_toks[0].lower()}&marketName={market}"
        return f"https://app.aave.com/markets/?marketName={market}"
    if "compound" in p:
        return f"https://app.compound.finance/markets/v3/{c}" if c else "https://app.compound.finance/markets"

    # ─── EVM AMM / LP (exact pool by address, else by token pair) ─────────
    if "curve" in p:
        # Llamalend = Curve LENDING, NOT an AMM pool. The /#/pools/{addr} form is
        # an AMM-only route — sending a llamalend market there lands on a WRONG
        # pool. Route to the llamalend section instead.
        if "llamalend" in p or "lend" in p:
            return f"https://curve.fi/llamalend/{c}/markets/" if c else "https://curve.fi/llamalend/"
        if addr:
            return f"https://curve.fi/#/{c}/pools/{addr}/deposit"
        return _fb()
    if "uniswap" in p:
        uc = _UNI_CHAIN.get(c, c)
        if addr:
            return f"https://app.uniswap.org/explore/pools/{uc}/{addr}"
        # NOTE: the old /add/{t0}/{t1} route was removed by Uniswap (404) — fall
        # through to the generic exact fallback instead of a dead link.
    if "pancakeswap" in p or p == "pancake":
        # V2 (amm) → /v2/add/{t0}/{t1} (deposit form, both tokens loaded).
        # V3 add REQUIRES the fee tier in the URL (/add/{t0}/{t1}/{fee}) or it
        # shows "Invalid pair"; this builder has no fee, so V3 routes to the
        # DexScreener exact pair (which has a Trade-on-PancakeSwap link). The
        # fee-aware V3 link is built in protocol_urls.pool_protocol_url.
        if "v3" not in p and len(evm_toks) >= 2:
            return f"https://pancakeswap.finance/v2/add/{evm_toks[0]}/{evm_toks[1]}"
        if addr and c:
            return f"https://dexscreener.com/{c}/{addr}"
    if "sushiswap" in p or p == "sushi":
        # Sushi's pool page is /pool/{chainId}%3A{addr} (version-agnostic — it
        # resolves V2 and V3 pools alike, so a mislabelled version is harmless).
        if addr:
            cid = _CHAIN_ID.get(c)
            if cid:
                return f"https://www.sushi.com/pool/{cid}%3A{addr}"
            return f"https://dexscreener.com/{c}/{addr}" if c else _fb()
    if "aerodrome" in p and addr:
        return f"https://aerodrome.finance/deposit?pool={addr}"
    if "velodrome" in p and addr:
        return f"https://velodrome.finance/deposit?pool={addr}"
    if "balancer" in p and addr:
        return f"https://balancer.fi/pools/{c}/v2/{addr}"

    # ─── Generic exact fallback (never a homepage / bare list) ────────────
    return _fb()
