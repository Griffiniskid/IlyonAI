"""One-click pool deposit: resolve a DefiLlama pool / protocol-pair into an
ExecutionPlanV3 the user signs in Phantom or MetaMask.

Bridges the gap between `search_defi_opportunities` (which lists pools) and
`build_yield_execution_plan` (which needs structured chain/protocol/action
inputs). The user can say "execute raydium-amm SPACEX-WSOL" or
"execute pool deaaa953-89d8-4c41-ac65-b354ff9d57d1" and this tool figures out
the rest.
"""
from __future__ import annotations

import asyncio
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import aiohttp

from src.agent.tools._base import err_envelope, ok_envelope
from src.agent.tools.build_yield_execution_plan import build_yield_execution_plan


_DEFILLAMA_POOL_URL = "https://yields.llama.fi/pool/{pool_id}"
_DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools"
_LLAMA_TIMEOUT = aiohttp.ClientTimeout(total=15)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _is_solana_pubkey(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip()
    if s.startswith("0x"):
        return False
    return bool(_BASE58_RE.match(s))


def _coerce_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _looks_like_pool_id(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip()))


# DefiLlama yields API has become paid-only (2026-Q2). When `/pools` returns
# a non-200 (404 / 402 / 5xx), fall back to a small curated catalog of the
# most-asked pool families so single-token pool intents still get a typed
# card response (pool_link redirect, prep-swap, or Aave/Compound supply
# adapter call) instead of a hard "pool_not_found" error.
_FALLBACK_POOL_CATALOG: list[dict[str, Any]] = [
    # ── EVM V3 ──
    {"chain": "Ethereum", "project": "uniswap-v3", "symbol": "USDC-WETH",
     "underlyingTokens": ["0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"],
     "pool": "fallback-uniswap-v3-eth-usdc-weth", "tvlUsd": 250_000_000, "apy": 14.0},
    {"chain": "Base", "project": "uniswap-v3", "symbol": "USDC-WETH",
     "underlyingTokens": ["0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "0x4200000000000000000000000000000000000006"],
     "pool": "fallback-uniswap-v3-base-usdc-weth", "tvlUsd": 80_000_000, "apy": 18.0},
    {"chain": "Arbitrum", "project": "uniswap-v3", "symbol": "USDC-WETH",
     "underlyingTokens": ["0xaf88d065e77c8cc2239327c5edb3a432268e5831", "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"],
     "pool": "fallback-uniswap-v3-arb-usdc-weth", "tvlUsd": 55_000_000, "apy": 12.0},
    {"chain": "BSC", "project": "pancakeswap-v3", "symbol": "USDT-WBNB",
     "underlyingTokens": ["0x55d398326f99059ff775485246999027b3197955", "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"],
     "pool": "fallback-pcs-v3-bsc-usdt-bnb", "tvlUsd": 120_000_000, "apy": 22.0},
    {"chain": "Base", "project": "aerodrome-slipstream", "symbol": "USDC-WETH",
     "underlyingTokens": ["0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "0x4200000000000000000000000000000000000006"],
     "pool": "fallback-aero-cl-base-usdc-weth", "tvlUsd": 35_000_000, "apy": 25.0},
    # ── EVM V2 / stable / vault ──
    {"chain": "Ethereum", "project": "curve-dex", "symbol": "3CRV",
     "underlyingTokens": ["0x6b175474e89094c44da98b954eedeac495271d0f", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0xdac17f958d2ee523a2206206994597c13d831ec7"],
     "pool": "fallback-curve-3pool", "tvlUsd": 200_000_000, "apy": 3.5},
    {"chain": "Ethereum", "project": "yearn-finance", "symbol": "yvUSDC",
     "underlyingTokens": ["0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"],
     "pool": "fallback-yearn-usdc", "tvlUsd": 45_000_000, "apy": 5.2},
    {"chain": "Ethereum", "project": "uniswap-v2", "symbol": "USDC-WETH",
     "underlyingTokens": ["0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"],
     "pool": "fallback-uniswap-v2-eth-usdc-weth", "tvlUsd": 15_000_000, "apy": 6.0},
    # ── Solana AMM / CLMM ──
    {"chain": "Solana", "project": "raydium-amm", "symbol": "SPACEX-WSOL",
     "underlyingTokens": ["So11111111111111111111111111111111111111112", "spacex_mint_placeholder"],
     "pool": "fallback-raydium-spacex-wsol", "tvlUsd": 4_500_000, "apy": 85.0},
    {"chain": "Solana", "project": "raydium-amm", "symbol": "USDC-SOL",
     "underlyingTokens": ["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "So11111111111111111111111111111111111111112"],
     "pool": "fallback-raydium-usdc-sol", "tvlUsd": 25_000_000, "apy": 18.0},
    {"chain": "Solana", "project": "orca-dex", "symbol": "USDC-SOL",
     "underlyingTokens": ["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "So11111111111111111111111111111111111111112"],
     "pool": "fallback-orca-usdc-sol", "tvlUsd": 35_000_000, "apy": 20.0},
    {"chain": "Solana", "project": "meteora-dlmm", "symbol": "SOL-USDC",
     "underlyingTokens": ["So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"],
     "pool": "fallback-meteora-sol-usdc", "tvlUsd": 22_000_000, "apy": 28.0},
]


def _fallback_pool_lookup(pool_id_or_ref: str) -> Optional[dict[str, Any]]:
    """Search the static catalog by pool id, project+symbol substring."""
    ref = (pool_id_or_ref or "").strip().lower()
    if not ref:
        return None
    for entry in _FALLBACK_POOL_CATALOG:
        if str(entry.get("pool", "")).lower() == ref:
            return entry
    return None


async def _fetch_pool_meta(pool_id: str) -> Optional[dict[str, Any]]:
    """Three-tier lookup chain:
       1. pool_index (DefiLlama refresher cache, sub-50ms — Phase 1.2 §1.2)
       2. DefiLlama live /pools fetch (rate-limited, often 404)
       3. Static fallback catalog (always available)
    """
    # Tier 1 — pool_index cache. Session factory is wired in production;
    # absent in dev env (skip silently).
    try:
        from src.storage.database import get_database  # type: ignore
        from src.defi.pool_index.store import find_pool_by_id
        db = get_database()
        session_factory = getattr(db, "_session_factory", None) if db else None
        if session_factory:
            async with session_factory() as session:
                row = await find_pool_by_id(session, pool_id=pool_id)
                if row:
                    return row
    except Exception:
        pass

    # Tier 2 — DefiLlama live.
    try:
        async with aiohttp.ClientSession(timeout=_LLAMA_TIMEOUT) as sess:
            async with sess.get(_DEFILLAMA_POOLS_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for entry in data.get("data") or []:
                        if str(entry.get("pool", "")).lower() == pool_id.lower():
                            return entry
    except Exception:
        pass

    # Tier 3 — static fallback.
    return _fallback_pool_lookup(pool_id)


async def _resolve_protocol_pair(
    protocol: str,
    pair: str,
    chain: Optional[str],
) -> Optional[dict[str, Any]]:
    """Find first DefiLlama pool whose project matches protocol AND symbol matches pair.

    Used for natural-language lookups like "raydium-amm SPACEX-WSOL".
    """
    proto_norm = protocol.lower().replace("_", "-").strip()
    pair_norm = pair.upper().replace("/", "-").replace("_", "-").strip()
    chain_norm = chain.lower() if chain else None
    looks_like_pair = bool(proto_norm) and "-" in proto_norm and proto_norm.replace("-", "").isupper()
    proto_filter_active = bool(proto_norm) and not looks_like_pair
    # When no protocol hint and no chain hint, bias toward chains we have
    # adapters for, in priority order. Avoids resolving 'USDC-WSOL' to
    # cetus-clmm on Sui when Orca/Raydium on Solana are the right hits.
    SUPPORTED_CHAIN_BIAS = {
        "solana": 1.4,
        "ethereum": 1.3,
        "polygon": 1.2,
        "arbitrum": 1.2,
        "base": 1.2,
        "optimism": 1.1,
        "bsc": 1.05,
        "avalanche": 1.0,
    }
    # Protocol-implied chain when not given.
    SOLANA_PROTOS = {"raydium", "orca", "meteora", "kamino", "marinade", "jito", "sanctum", "drift", "lulo"}
    EVM_PROTOS = {"aave", "compound", "yearn", "lido", "rocket-pool", "ether.fi", "morpho", "spark", "curve", "convex", "pendle", "stargate", "frax"}
    if not chain_norm and proto_norm:
        head = proto_norm.split("-")[0]
        if head in SOLANA_PROTOS:
            chain_norm = "solana"
        elif head in EVM_PROTOS:
            pass
    # Family-head fallback. DefiLlama collapses many variants into one slug
    # (Raydium AMM v4 + CPMM + CLMM all live under project="raydium-amm"; no
    # separate "raydium-clmm"). When the user names a sub-variant the strict
    # substring filter rejects every entry. So if proto_norm carries a
    # hyphen, also accept entries whose project starts with the same head.
    proto_head_match = proto_norm.split("-")[0] if proto_norm else ""

    def _proto_ok(project: str) -> bool:
        if not proto_filter_active:
            return True
        if proto_norm in project or project in proto_norm:
            return True
        if proto_head_match and project.split("-")[0] == proto_head_match:
            return True
        return False

    def _match_catalog(catalog: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        best: Optional[dict[str, Any]] = None
        best_score = -1.0
        # Allow WSOL/SOL parity in the pair filter — DefiLlama almost always
        # uses the wrapped form on Solana entries even when the user says
        # "SOL". Same for ETH/WETH on EVM. Keeping the user's words honest in
        # the UI while letting the catalog match the wrapped variant.
        def _pair_variants(pn: str) -> list[str]:
            base = [pn, "-".join(reversed(pn.split("-")))]
            extras: list[str] = []
            for v in base:
                w = v
                for raw, wrap in (("WSOL", "SOL"), ("SOL", "WSOL"), ("WETH", "ETH"), ("ETH", "WETH"), ("WBNB", "BNB"), ("BNB", "WBNB")):
                    if raw in w:
                        extras.append(w.replace(raw, wrap))
            return list({*base, *extras})

        for entry in catalog:
            project = str(entry.get("project", "")).lower()
            symbol = str(entry.get("symbol", "")).upper().replace("/", "-")
            ec = str(entry.get("chain", "")).lower()
            if not _proto_ok(project):
                continue
            if chain_norm and chain_norm not in ec:
                continue
            if pair_norm:
                if not any(v in symbol for v in _pair_variants(pair_norm)):
                    continue
            tvl = float(entry.get("tvlUsd") or 0)
            bias = SUPPORTED_CHAIN_BIAS.get(ec, 0.7)
            # Exact-slug match (or substring containment) wins over head-only
            # fallback by 100×, so 'jupiter-perps' matches 'jupiter-perps'
            # before settling for 'jupiter-lend' just because both heads are
            # 'jupiter'. Without this weighting the head fallback silently
            # substitutes one Jupiter product for another.
            proto_score_mult = 1.0
            if proto_filter_active:
                if proto_norm and proto_norm in project:
                    proto_score_mult = 100.0
                elif project and project in proto_norm:
                    proto_score_mult = 100.0
            score = tvl * bias * proto_score_mult
            if score > best_score:
                best = entry
                best_score = score
        return best

    try:
        async with aiohttp.ClientSession(timeout=_LLAMA_TIMEOUT) as sess:
            async with sess.get(_DEFILLAMA_POOLS_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    entries = data.get("data") or []
                    matched = _match_catalog(entries)
                    if matched is not None:
                        return matched
    except Exception:
        pass

    # Fallback: search the static catalog. Honest: APY/TVL fields are
    # estimates from the snapshot date, not live. Sufficient for routing
    # the user to a real pool deeplink + correct pair-aware Solana zap.
    return _match_catalog(_FALLBACK_POOL_CATALOG)


def _split_protocol_pair(arg: str) -> tuple[str, str]:
    """Accept 'raydium-amm · SPACEX-WSOL', 'raydium-amm SPACEX-WSOL',
    'raydium-amm/SPACEX-WSOL', or a bare 'SPACEX-WSOL' pair.
    """
    cleaned = arg.replace("·", " ").replace("|", " ").strip()
    parts = [p for p in re.split(r"\s+", cleaned) if p]
    if len(parts) == 0:
        return "", ""
    if len(parts) == 1:
        only = parts[0]
        # If it has a separator it's already a pair; treat protocol as empty.
        if any(sep in only for sep in ("-", "/", "_")) and only.isupper():
            return "", only
        return only, ""
    # If first chunk hyphenated like "raydium-amm" keep it intact.
    return parts[0], parts[-1]


def _pick_asset_in(meta: dict[str, Any]) -> str:
    """Pick a sensible asset to deposit. Prefer USDC when present, else first
    underlying token, else the symbol's first leg.
    """
    underlying = meta.get("underlyingTokens") or []
    symbols = []
    sym = str(meta.get("symbol", ""))
    if "-" in sym:
        symbols = sym.split("-")
    elif "/" in sym:
        symbols = sym.split("/")
    if any(s.upper() == "USDC" for s in symbols):
        return "USDC"
    if symbols:
        return symbols[0].upper()
    if underlying:
        return "USDC"
    return "USDC"


# V7-044: The hardcoded ``_TOKEN_USD_HINT_LOCAL`` dict (WETH=2300 / WBTC=80000)
# was removed. USD→native conversion now reads the live oracle cache via
# ``get_cached_price_usd_sync``. On cache miss the conversion is skipped
# (native amount preserved) — the downstream async adapter re-prices.

_STABLE_TICKERS = {"USDC", "USDT", "USD", "DAI", "FRAX", "USDE", "GHO", "PYUSD",
                   "TUSD", "BUSD", "FDUSD", "MIM", "MKUSD", "CRVUSD", "USDS", "SUSDS",
                   "USDD", "USDX", "AUSD", "USDY", "MUSD"}


async def execute_pool_position(
    ctx,
    *,
    pool: str,
    amount: Any,
    asset_in: str | None = None,
    chain: str | None = None,
    user_address: str | None = None,
    slippage_bps: int = 50,
    research_thesis: str | None = None,
    amount_is_usd: bool = False,
    extra: dict[str, Any] | None = None,
):
    """One-shot pool deposit. `pool` may be a DefiLlama pool UUID or a
    'protocol pair' string like 'raydium-amm SPACEX-WSOL'.
    """
    if not pool:
        return err_envelope("missing_pool", "Provide a pool UUID or 'protocol pair' string.")
    amt = _coerce_amount(amount)
    if amt <= 0:
        return err_envelope("invalid_amount", "amount must be a positive decimal value.")

    if not user_address:
        # Try ctx wallets in order. We re-pick after meta resolves to
        # ensure we use the right one for the pool's chain.
        user_address = (
            getattr(ctx, "wallet", None)
            or getattr(ctx, "solana_wallet", None)
            or getattr(ctx, "evm_wallet", None)
        )
    if not user_address:
        return err_envelope(
            "missing_wallet",
            "Connect a wallet before requesting a pool deposit; the plan needs a destination address.",
        )

    # F02 protocol-chain matrix — reject combos like aave-v3 on solana,
    # marinade on ethereum at the execute_pool_position entry too (mirrors
    # the matrix in build_yield_execution_plan; this tool is sometimes
    # dispatched ahead of it by _detect_direct_pool_deposit).
    _EVM_ONLY_PROTOS_LC = {
        "aave-v3", "aave", "compound-v3", "compound", "morpho-blue", "morpho",
        "spark", "sparklend", "yearn-finance", "yearn", "lido", "rocket-pool",
        "ether.fi", "etherfi", "renzo", "swell", "frax-ether", "frax",
        "mantle-staked-ether", "kelp", "uniswap-v3", "uniswap-v2", "uniswap-v4",
        "uniswap", "pancakeswap-amm-v3", "pancakeswap", "balancer-v3", "balancer",
        "curve-dex", "curve", "convex", "pendle", "stargate", "gmx", "velodrome",
        "aerodrome", "aerodrome-slipstream", "moonwell", "stader",
        "sky-savings-rate", "sky",
    }
    _SOLANA_ONLY_PROTOS_LC = {
        "raydium", "raydium-amm", "raydium-clmm", "raydium-cp",
        "orca", "orca-dex", "orca-whirlpools",
        "meteora", "meteora-dlmm", "meteora-vault", "meteora-amm",
        "kamino", "kamino-liquidity", "kamino-lend", "kamino-vault",
        "marinade", "marinade-liquid-staking", "marinade-native",
        "jito", "jito-liquid-staking",
        "sanctum", "sanctum-infinity", "sanctum-liquid-staking",
        "jlp", "jupiter-perps", "jupiter-perpetuals",
        "drift", "phoenix", "openbook", "gmtrade",
    }
    pool_head_lc = str(pool).strip().split()[0].lower() if pool else ""
    chain_lc = (chain or "").lower()
    if chain_lc in {"solana", "sol"} and pool_head_lc in _EVM_ONLY_PROTOS_LC:
        return err_envelope(
            "unsupported_chain",
            f"{pool_head_lc} is an EVM-only protocol — it does not exist on Solana. "
            f"Use Kamino Lend or MarginFi for Solana lending, or switch to Ethereum / "
            f"Base / Arbitrum / Optimism for {pool_head_lc}.",
        )
    if chain_lc and chain_lc not in {"solana", "sol"} and pool_head_lc in _SOLANA_ONLY_PROTOS_LC:
        return err_envelope(
            "unsupported_chain",
            f"{pool_head_lc} is a Solana-only protocol — it does not exist on "
            f"{chain_lc.title()}. Use Aave V3 / Compound / Morpho for {chain_lc.title()} lending, "
            f"or switch to Solana for {pool_head_lc}.",
        )

    pool_arg = str(pool).strip()
    meta: Optional[dict[str, Any]] = None

    # Common-name → canonical-slug aliases. Lets users say "Whirlpool" /
    # "Slipstream" / "DLMM" without knowing the DefiLlama slug.
    _POOL_NAME_ALIASES = {
        "whirlpool": "orca-whirlpools",
        "whirlpools": "orca-whirlpools",
        "orca-whirlpool": "orca-whirlpools",
        "dlmm": "meteora-dlmm",
        "slipstream": "aerodrome-slipstream",
        "uni-v3": "uniswap-v3",
        "uni-v4": "uniswap-v4",
        "pancake": "pancakeswap",
        "v3": "uniswap-v3",
    }
    # Apply alias rewrite if the first token of pool_arg matches.
    _pool_parts = pool_arg.split(maxsplit=1)
    if _pool_parts:
        _head = _pool_parts[0].lower()
        if _head in _POOL_NAME_ALIASES:
            pool_arg = " ".join([_POOL_NAME_ALIASES[_head], *_pool_parts[1:]])

    if _looks_like_pool_id(pool_arg):
        meta = await _fetch_pool_meta(pool_arg)
    else:
        protocol_hint, pair_hint = _split_protocol_pair(pool_arg)
        # Infer chain from a Solana protocol head when not given so the
        # final retry stays on Solana even after we drop the proto filter.
        SOLANA_PROTOS = {"raydium", "orca", "meteora", "kamino", "marinade", "jito", "sanctum", "drift", "lulo", "save", "lifinity", "solend"}
        # Known protocol family heads. When the user explicitly types a
        # protocol name and it isn't a known family, we MUST refuse rather
        # than fall through to a pair-only search — that fallback used to
        # silently substitute "FakeBank USDC" → "Maple V2 USDC" because
        # Maple was the highest-TVL USDC pool on Ethereum.
        KNOWN_PROTO_HEADS = SOLANA_PROTOS | {
            "aave", "compound", "yearn", "lido", "rocket-pool", "rocketpool",
            "ether.fi", "etherfi", "morpho", "spark", "curve", "convex",
            "pendle", "stargate", "frax", "uniswap", "pancakeswap",
            "sushiswap", "balancer", "velodrome", "aerodrome", "camelot",
            "trader-joe", "traderjoe", "ramses", "thena", "moonwell",
            "benqi", "mendi", "venus", "radiant", "silo", "fluid",
            "iearn", "beefy", "yearn-v3", "yearn-v2", "yearn-v1",
            "stader", "ankr", "swell", "kelp", "puffer", "renzo",
            "eigenlayer", "fraxlend", "fraxswap", "gmx", "hyperliquid",
            "ethena", "usual", "resolv", "anzen", "maple",
        }
        inferred_chain = chain
        proto_head = protocol_hint.split("-")[0].lower() if protocol_hint else ""
        if not inferred_chain and proto_head in SOLANA_PROTOS:
            inferred_chain = "solana"
        meta = await _resolve_protocol_pair(protocol_hint, pair_hint, chain=inferred_chain)
        if not meta and inferred_chain:
            meta = await _resolve_protocol_pair(protocol_hint, pair_hint, chain=None)
        # Only drop the protocol filter when (a) the user didn't name a
        # protocol, or (b) the named protocol is a known family that
        # might just be missing this exact suffix (raydium-clmm → raydium).
        # Refuse to silently substitute when the user names something the
        # catalog never heard of (e.g. "FakeBank", "WashBank").
        protocol_known = (not protocol_hint) or proto_head in KNOWN_PROTO_HEADS
        if not meta and pair_hint and protocol_known:
            meta = await _resolve_protocol_pair("", pair_hint, chain=inferred_chain)
        if not meta and protocol_hint and not pair_hint and protocol_known:
            meta = await _resolve_protocol_pair("", protocol_hint, chain=inferred_chain)
        # Final guard: if the user explicitly named a protocol, the matched
        # pool must belong to the same family head. Catches the case where
        # broadening the search silently substitutes "raydium-clmm SOL-USDC"
        # → "orca-dex SOL-USDC" because they share the pair.
        if meta and protocol_hint and proto_head:
            matched_project = str(meta.get("project", "")).lower()
            matched_head = matched_project.split("-")[0]
            if matched_head and matched_head != proto_head:
                meta = None

    if not meta:
        # Emit a structured blocker card so the chat shows an actionable
        # "pool not found" panel instead of a silent error. The frontend
        # already knows how to render execution_plan_v3 blockers (rose
        # banner + CTA), so we re-use it here for unknown-protocol /
        # unknown-pair requests like "Supply 5 USDT to FakeBank on Solana".
        from src.defi.execution.models import ExecutionBlocker, ExecutionPlanV3
        plan = ExecutionPlanV3.new(
            title="Pool not found",
            summary=f"Couldn't match `{pool_arg}` to a DefiLlama pool.",
        )
        _blocker = ExecutionBlocker(
            code="pool_not_found",
            severity="blocker",
            title="No matching pool",
            detail=(
                f"`{pool_arg}` did not match any pool in the live DefiLlama catalog. "
                "Try a tighter reference: paste the DefiLlama pool UUID, or use 'protocol pair' "
                "(e.g. 'raydium-amm SOL-USDC', 'aave-v3 USDC')."
            ),
            affected_step_ids=[],
            recoverable=True,
            cta="Re-send with a recognized protocol + pair.",
        )
        # V7-066 — enrich with structured recovery posture before adding to plan.
        from src.defi.recovery import FailureKind, enrich_blocker_with_recovery
        enrich_blocker_with_recovery(
            _blocker,
            FailureKind.POOL_REMOVED,
            step_kind="deposit",
            pool_id=str(pool_arg),
        )
        plan.add_blocker(_blocker)
        return ok_envelope(data={"plan": plan.to_dict()}, card_type="execution_plan_v3", card_payload=plan.to_dict())

    chain = str(meta.get("chain", "")).lower()
    protocol = str(meta.get("project", "")).lower()
    pool_symbol = str(meta.get("symbol", ""))

    # Preserve the user's sub-variant when they explicitly named it. DefiLlama
    # collapses every Raydium variant into 'raydium-amm'; if the user asked
    # for 'raydium-clmm' the downstream range_block emitter needs to know,
    # and the title should reflect the user's named protocol. Use the
    # alias-rewritten pool_arg so 'Whirlpool USDC-SOL' → 'orca-whirlpools'
    # also gets preserved when DefiLlama only knows 'orca-dex'.
    try:
        _user_proto_hint, _ = _split_protocol_pair(pool_arg)
    except Exception:
        _user_proto_hint = ""
    _user_proto_l = (_user_proto_hint or "").lower()
    _CLMM_SUB_VARIANTS = {
        "raydium-clmm", "raydium-amm-v3",
        "orca-clmm", "orca-whirlpools",
        "meteora-dlmm",
    }
    if _user_proto_l in _CLMM_SUB_VARIANTS:
        _user_head = _user_proto_l.split("-")[0]
        _matched_head = protocol.split("-")[0]
        if _user_head == _matched_head:
            protocol = _user_proto_l

    # Dual-token V2 override: when the caller passed extra.dual_token=True the
    # user has explicitly named a V2/V1 protocol form (uniswap-v2, sushiswap,
    # pancakeswap-v2, etc.) and provided both legs. Trust the user — force
    # `protocol` back to their explicit reference so the meta lookup can't
    # drift to a V3 / CLMM / Slipstream variant of the same family, or to a
    # totally unrelated catalog entry (e.g. Beefy when DefiLlama returns the
    # first Beefy vault that happens to mirror the pair).
    if extra and extra.get("dual_token"):
        try:
            user_proto_hint, _ = _split_protocol_pair(str(pool).strip())
        except Exception:
            user_proto_hint = ""
        user_proto_l = (user_proto_hint or "").lower()
        if user_proto_l:
            protocol = user_proto_l

    final_asset_in = asset_in or _pick_asset_in(meta)

    # USD-denominated amount → native units conversion. When the user typed
    # "$100" or "with 100 USDC" but the pool's primary asset is non-stable
    # (WSOL, ETH, BTC, etc.), the raw amount must be re-denominated into the
    # source asset's native units. Otherwise "100" gets sent as 100 WSOL
    # (~$9,400) and the wallet popup shows "Not enough SOL".
    final_asset_upper = (final_asset_in or "").upper()
    if amount_is_usd and final_asset_upper not in _STABLE_TICKERS:
        from src.data.price_oracle import get_cached_price_usd_sync
        usd_price = get_cached_price_usd_sync(final_asset_upper)
        if usd_price and usd_price > 0:
            from decimal import Decimal
            amt_float = float(amt) if not isinstance(amt, float) else amt
            converted = amt_float / usd_price
            # Guard: never convert below 0.0001 (dust).
            if converted >= 0.0001:
                amt = converted

    # Wallet/chain compatibility preflight. If the primary wallet is the
    # wrong format for this pool, swap in the matching ctx field before
    # giving up. Phantom in dual-mode exposes both an EVM hex address and
    # a Solana base58 pubkey — both come through, just under different
    # request body fields.
    is_solana_pool = chain in {"solana", "sol"}
    is_evm_pool = chain in {"ethereum", "polygon", "arbitrum", "base", "optimism", "bsc", "avalanche"}
    if is_solana_pool and not _is_solana_pubkey(user_address):
        sol_alt = getattr(ctx, "solana_wallet", None)
        if sol_alt and _is_solana_pubkey(sol_alt):
            user_address = sol_alt
    if is_evm_pool and not (isinstance(user_address, str) and user_address.lower().startswith("0x") and len(user_address) == 42):
        evm_alt = getattr(ctx, "evm_wallet", None)
        if evm_alt and evm_alt.startswith("0x") and len(evm_alt) == 42:
            user_address = evm_alt
    user_is_solana = _is_solana_pubkey(user_address)
    user_is_evm = isinstance(user_address, str) and user_address.lower().startswith("0x") and len(user_address) == 42
    if is_solana_pool and not user_is_solana:
        from src.defi.execution.models import ExecutionBlocker, ExecutionPlanV3
        from src.agent.tools.build_yield_execution_plan import humanize_protocol
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} Deposit",
            summary=f"{humanize_protocol(protocol)} {pool_symbol} requires a Solana wallet.",
        )
        _blocker = ExecutionBlocker(
            code="WALLET_CHAIN_MISMATCH",
            severity="blocker",
            title="Wrong wallet for this pool",
            detail=(
                f"This pool is on Solana ({protocol} {pool_symbol}). Your connected wallet "
                f"`{(user_address or '')[:12]}…` looks EVM (or otherwise non-Solana). "
                "Switch to a Solana wallet (Phantom in Solana mode) and retry."
            ),
            affected_step_ids=[],
            cta="Connect a Solana wallet (Phantom) to sign this deposit.",
        )
        # V7-066 — wire decide_recovery with the typed WALLET_CHAIN_MISMATCH kind.
        from src.defi.recovery import FailureKind, enrich_blocker_with_recovery
        enrich_blocker_with_recovery(
            _blocker,
            FailureKind.WALLET_CHAIN_MISMATCH,
            step_kind="deposit",
            pool_id=str(meta.get("pool", "")),
        )
        plan.add_blocker(_blocker)
        return ok_envelope(data={"plan": plan.to_dict()}, card_type="execution_plan_v3", card_payload=plan.to_dict())
    if is_evm_pool and not user_is_evm:
        from src.defi.execution.models import ExecutionBlocker, ExecutionPlanV3
        from src.agent.tools.build_yield_execution_plan import humanize_protocol
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} Deposit",
            summary=f"{humanize_protocol(protocol)} {pool_symbol} on {chain[:1].upper()+chain[1:]} requires an EVM wallet.",
        )
        _blocker = ExecutionBlocker(
            code="WALLET_CHAIN_MISMATCH",
            severity="blocker",
            title="Wrong wallet for this pool",
            detail=(
                f"This pool is on {chain} ({protocol} {pool_symbol}). Your connected wallet "
                f"`{(user_address or '')[:12]}…` looks Solana (or otherwise non-EVM). "
                "Switch to MetaMask (or Phantom in EVM mode) and retry."
            ),
            affected_step_ids=[],
            cta="Connect an EVM wallet (MetaMask) to sign this deposit.",
        )
        # V7-066 — wire decide_recovery with the typed WALLET_CHAIN_MISMATCH kind.
        from src.defi.recovery import FailureKind, enrich_blocker_with_recovery
        enrich_blocker_with_recovery(
            _blocker,
            FailureKind.WALLET_CHAIN_MISMATCH,
            step_kind="deposit",
            pool_id=str(meta.get("pool", "")),
        )
        plan.add_blocker(_blocker)
        return ok_envelope(data={"plan": plan.to_dict()}, card_type="execution_plan_v3", card_payload=plan.to_dict())

    # Solana non-LP / non-Jupiter-tradable protocols. We have NO native sign
    # path for these and the sidecar's Jupiter pre-swap always 400s because
    # the receipt mint isn't in Jupiter's swap graph. Emit a clean
    # `pool_kind_unsupported` blocker with a deeplink to the protocol UI so
    # the user can complete the deposit there instead of staring at a raw
    # "Jupiter quote returned 400" leak.
    _SOLANA_NON_LP_PROTOS = {
        "gmtrade",  # synthetic perps — LP mints absent from Jupiter
        "phoenix", "phoenix-v1",  # CLOB, no AMM LP
        "openbook", "openbook-v2",  # CLOB
        "drift", "drift-perp-vaults", "drift-vaults",  # perps vaults
        "lulo",  # deposit market, no fungible receipt
        "save", "save-finance",  # lending market
        "marginfi", "mfi",  # lending market
        "mango", "mango-markets",  # CLOB perps
        "perena",  # synthetic stablecoin
        "fluxbeam",  # long-tail
        "cropper", "cropper-finance",  # long-tail AMM
        "aldrin", "crema", "crema-finance",  # long-tail AMM
        "ondo-finance",  # treasury fund
        "exponent",
        "huma", "loopscale", "sentre-protocol",
        "swissborg",
    }
    if chain.lower() in {"solana", "sol"} and protocol.lower() in _SOLANA_NON_LP_PROTOS:
        from src.defi.execution.models import ExecutionBlocker, ExecutionPlanV3
        from src.agent.tools.build_yield_execution_plan import humanize_protocol
        # Pull the protocol's app URL if known; fall back to DefiLlama.
        try:
            from src.agent.protocol_urls import protocol_app_url
            link = protocol_app_url(protocol) or f"https://defillama.com/protocol/{protocol}"
        except Exception:
            link = f"https://defillama.com/protocol/{protocol}"
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {pool_symbol}",
            summary=(
                f"{humanize_protocol(protocol)} {pool_symbol} is not yet wired for one-click "
                "execution from IlyonAI."
            ),
        )
        _blocker = ExecutionBlocker(
            code="pool_kind_unsupported",
            severity="blocker",
            title="Pool not supported for one-click deposit",
            detail=(
                f"{humanize_protocol(protocol)} deposits on Solana require a protocol-specific "
                "transaction that isn't routable through Jupiter (the receipt mint isn't on the "
                "swap graph). Use the protocol UI directly for now — your funds stay safe."
            ),
            affected_step_ids=[],
            recoverable=True,
            cta=f"Open {humanize_protocol(protocol)} to deposit there: {link}",
        )
        # V7-066 — surface a recovery posture even when we cannot one-click.
        from src.defi.recovery import FailureKind, enrich_blocker_with_recovery
        enrich_blocker_with_recovery(
            _blocker,
            FailureKind.POOL_REMOVED,
            step_kind="deposit",
            pool_id=str(meta.get("pool", "")),
        )
        plan.add_blocker(_blocker)
        return ok_envelope(data={"plan": plan.to_dict()}, card_type="execution_plan_v3", card_payload=plan.to_dict())

    is_lp = "-" in pool_symbol or "/" in pool_symbol
    action = "deposit_lp" if is_lp else "supply"

    extra_out: dict[str, Any] = {
        "pool_id": meta.get("pool"),
        "pool_symbol": pool_symbol,
    }
    if meta.get("underlyingTokens"):
        extra_out["underlying_tokens"] = meta.get("underlyingTokens")
    # DefiLlama APY/APY components for range_block.market — drops the 0%
    # placeholder we used to render for V3 EVM pools whose ticks resolved
    # but whose yield wasn't surfaced from the catalog.
    if meta.get("apy") is not None:
        extra_out["apy_total"] = float(meta.get("apy") or 0.0)
    if meta.get("apyBase") is not None:
        extra_out["apy_base"] = float(meta.get("apyBase") or 0.0)
    if meta.get("apyReward") is not None:
        extra_out["apy_reward"] = float(meta.get("apyReward") or 0.0)
    if meta.get("tvlUsd") is not None:
        extra_out["tvl_usd"] = float(meta.get("tvlUsd") or 0.0)
    # Caller-supplied extra (e.g. dual-token V2 amounts from the parser) wins
    # over the meta-derived defaults so adapters can rely on it.
    if extra:
        extra_out.update(extra)
    extra = extra_out
    if chain.lower() in {"solana", "sol"}:
        # Solana yield-builder accepts an optional `lpMint` to skip the
        # prep-swap and route a single one-tx deposit into the LP token.
        # Only attach it when we have a real base58 Solana mint AND the
        # protocol is one whose LP is actually a fungible Jupiter-routable
        # mint (Sanctum LSTs, Marinade mSOL, etc.). For Raydium AMM v4 /
        # Orca AMM, underlyingTokens are pair tokens (e.g. AURA), not the
        # LP mint — passing them as lpMint causes Jupiter to 400 because
        # the meme token isn't on Jupiter's tradable list. Always fall
        # through to the prep-swap path for AMM-style pools.
        AMM_PROTOS_NO_LPMINT = {
            "raydium", "raydium-amm", "raydium-amm-v3", "raydium-clmm", "raydium-cp",
            "orca", "orca-dex", "orca-whirlpools", "orca-clmm",
            "meteora", "meteora-dlmm", "meteora-amm", "meteora-vault",
            "lifinity", "lifinity-v2",
            "kamino-liquidity", "blackhole-clmm", "supernova-cl",
            "shadow-exchange-clmm", "steer-protocol", "gmtrade",
        }
        if protocol.lower() not in AMM_PROTOS_NO_LPMINT:
            candidates = []
            if meta.get("pool_address") or meta.get("poolAddress"):
                candidates.append(meta.get("pool_address") or meta.get("poolAddress"))
            for tok in (meta.get("underlyingTokens") or []):
                candidates.append(tok)
            valid = next((c for c in candidates if _is_solana_pubkey(c)), None)
            if valid:
                extra["lpMint"] = valid

    return await build_yield_execution_plan(
        ctx,
        chain=chain,
        protocol=protocol,
        action=action,
        asset_in=final_asset_in,
        amount_in=amt,
        user_address=user_address,
        slippage_bps=slippage_bps,
        research_thesis=research_thesis or f"Direct deposit into {protocol} {pool_symbol} on {chain}.",
        extra=extra,
    )
