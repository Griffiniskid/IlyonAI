"""Build a deep link to a SPECIFIC pool's deposit page on the correct protocol.

When a pool can't be one-click executed, the UI shows an "Open pool" button
that must take the user straight to *that pool* on the protocol's own app — not
the protocol homepage. When we don't have enough on-chain identity to build the
protocol-native URL, we fall back to the DefiLlama *pool* page, which is still
the exact pool (never a homepage).
"""
from __future__ import annotations

_DEFILLAMA_POOL = "https://defillama.com/yields/pool/{uuid}"


def _n(value: str | None) -> str:
    return (value or "").lower().strip()


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
    addr = pool_address
    mints = [m for m in (underlying_tokens or []) if m]

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
        return _DEFILLAMA_POOL.format(uuid=pool_id)

    # ─── EVM ──────────────────────────────────────────────────────────────
    if "curve" in p and addr:
        return f"https://curve.fi/#/{c}/pools/{addr}/deposit"
    if "uniswap" in p and addr:
        return f"https://app.uniswap.org/explore/pools/{c}/{addr}"
    if "pancakeswap" in p and addr:
        return f"https://pancakeswap.finance/liquidity/pool/{c}/{addr}"
    if "sushiswap" in p and addr:
        return f"https://www.sushi.com/{c}/pool/v2/{addr}"
    if "aerodrome" in p and addr:
        return f"https://aerodrome.finance/deposit?pool={addr}"
    if "velodrome" in p and addr:
        return f"https://velodrome.finance/deposit?pool={addr}"
    if "balancer" in p and addr:
        return f"https://balancer.fi/pools/{c}/v2/{addr}"
    if "aave" in p:
        return "https://app.aave.com/markets/"
    if "compound" in p:
        return "https://app.compound.finance/"

    # ─── Fallback: DefiLlama exact-pool page (still the specific pool) ─────
    return _DEFILLAMA_POOL.format(uuid=pool_id)
