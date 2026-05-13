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
    """DefiLlama doesn't have a single-pool endpoint; we hit /pools and filter.
    Cached by adapter, so fine for one-off lookups. Falls back to the static
    catalog when DefiLlama is unreachable (yields API became paid-only in
    2026-Q2 so /pools returns 404 globally on free callers).
    """
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
    def _match_catalog(catalog: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        best: Optional[dict[str, Any]] = None
        best_score = -1.0
        for entry in catalog:
            project = str(entry.get("project", "")).lower()
            symbol = str(entry.get("symbol", "")).upper().replace("/", "-")
            ec = str(entry.get("chain", "")).lower()
            if proto_filter_active and proto_norm not in project and project not in proto_norm:
                continue
            if chain_norm and chain_norm not in ec:
                continue
            if pair_norm:
                pair_alt = "-".join(reversed(pair_norm.split("-")))
                if pair_norm not in symbol and pair_alt not in symbol:
                    continue
            tvl = float(entry.get("tvlUsd") or 0)
            bias = SUPPORTED_CHAIN_BIAS.get(ec, 0.7)
            score = tvl * bias
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


_TOKEN_USD_HINT_LOCAL: dict[str, float] = {
    "SOL": 90.0, "WSOL": 90.0,
    "ETH": 2300.0, "WETH": 2300.0, "STETH": 2300.0, "WSTETH": 2400.0, "WEETH": 2400.0,
    "BNB": 640.0, "WBNB": 640.0,
    "MATIC": 0.13, "WMATIC": 0.13, "POL": 0.13,
    "AVAX": 18.0, "WAVAX": 18.0,
    "BTC": 80000.0, "WBTC": 80000.0, "CBBTC": 80000.0, "BTC.B": 80000.0,
    "ARB": 0.13, "OP": 0.15, "AERO": 0.95, "VELO": 0.05,
    "USDC": 1.0, "USDT": 1.0, "DAI": 1.0, "FRAX": 1.0, "USDE": 1.0, "SUSDE": 1.05,
    "GHO": 1.0, "PYUSD": 1.0, "TUSD": 1.0, "BUSD": 1.0, "FDUSD": 1.0,
    "MIM": 1.0, "MKUSD": 1.0, "CRVUSD": 1.0, "USDS": 1.0, "SUSDS": 1.05,
}

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

    pool_arg = str(pool).strip()
    meta: Optional[dict[str, Any]] = None

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
        plan.add_blocker(ExecutionBlocker(
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
        ))
        return ok_envelope(data={"plan": plan.to_dict()}, card_type="execution_plan_v3", card_payload=plan.to_dict())

    chain = str(meta.get("chain", "")).lower()
    protocol = str(meta.get("project", "")).lower()
    pool_symbol = str(meta.get("symbol", ""))

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
        usd_price = _TOKEN_USD_HINT_LOCAL.get(final_asset_upper)
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
        plan.add_blocker(ExecutionBlocker(
            code="wallet_chain_mismatch",
            severity="blocker",
            title="Wrong wallet for this pool",
            detail=(
                f"This pool is on Solana ({protocol} {pool_symbol}). Your connected wallet "
                f"`{(user_address or '')[:12]}…` looks EVM (or otherwise non-Solana). "
                "Switch to a Solana wallet (Phantom in Solana mode) and retry."
            ),
            affected_step_ids=[],
            cta="Connect a Solana wallet (Phantom) to sign this deposit.",
        ))
        return ok_envelope(data={"plan": plan.to_dict()}, card_type="execution_plan_v3", card_payload=plan.to_dict())
    if is_evm_pool and not user_is_evm:
        from src.defi.execution.models import ExecutionBlocker, ExecutionPlanV3
        from src.agent.tools.build_yield_execution_plan import humanize_protocol
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} Deposit",
            summary=f"{humanize_protocol(protocol)} {pool_symbol} on {chain[:1].upper()+chain[1:]} requires an EVM wallet.",
        )
        plan.add_blocker(ExecutionBlocker(
            code="wallet_chain_mismatch",
            severity="blocker",
            title="Wrong wallet for this pool",
            detail=(
                f"This pool is on {chain} ({protocol} {pool_symbol}). Your connected wallet "
                f"`{(user_address or '')[:12]}…` looks Solana (or otherwise non-EVM). "
                "Switch to MetaMask (or Phantom in EVM mode) and retry."
            ),
            affected_step_ids=[],
            cta="Connect an EVM wallet (MetaMask) to sign this deposit.",
        ))
        return ok_envelope(data={"plan": plan.to_dict()}, card_type="execution_plan_v3", card_payload=plan.to_dict())

    is_lp = "-" in pool_symbol or "/" in pool_symbol
    action = "deposit_lp" if is_lp else "supply"

    extra_out: dict[str, Any] = {
        "pool_id": meta.get("pool"),
        "pool_symbol": pool_symbol,
    }
    if meta.get("underlyingTokens"):
        extra_out["underlying_tokens"] = meta.get("underlyingTokens")
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
