"""Build a real ExecutionPlanV3 for a specific yield action through registry adapters."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from src.agent.protocol_urls import classify_pool_kind, is_pool_link_action, pool_protocol_url
from src.agent.tools._base import err_envelope, ok_envelope
from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.capabilities import build_default_registry
from src.defi.execution.models import ExecutionBlocker, ExecutionPlanV3
from src.defi.execution.preflight import WalletInventory, evaluate_preflight
from src.defi.strategy.memory import StrategyRecord, remember_strategy


def _synth_cdf_30d(sym0: str, sym1: str) -> list[dict[str, float]]:
    """Synthetic 30-day price-ratio CDF for the V3 range card.

    Real implementation would fetch CoinGecko hourly prices over 30 days and
    compute empirical CDF over price-ratio buckets. Until that's wired, emit
    a smooth Gaussian-like CDF anchored to current price (ratio=1.0) so the
    frontend always has 30+ samples to render the in-range probability curve.
    Volatility is heuristic-tightened for stable pairs and widened for blue
    chips. Frontend can replace with live CDF when available.
    """
    import math

    a, b = (sym0 or "").upper(), (sym1 or "").upper()
    stables = {"USDC", "USDT", "DAI", "FRAX", "LUSD", "USDS", "TUSD", "BUSD",
               "FDUSD", "USDBC", "USDE", "SDAI", "SUSDE"}
    if a in stables and b in stables:
        sigma = 0.003  # 0.3% std dev — peg-tight
    elif a in stables or b in stables:
        sigma = 0.18  # 18% std dev — blue-chip vs stable
    else:
        sigma = 0.30  # exotic / blue-blue cross

    samples = []
    for i in range(30):
        # 30 buckets across [0.4, 2.5] ratio range
        t = i / 29.0
        ratio = 0.4 + (2.5 - 0.4) * t
        # Approximate Gaussian CDF via tanh
        z = (math.log(ratio)) / sigma
        cdf = 0.5 * (1.0 + math.tanh(z * 0.7978))  # erf(z/sqrt(2)) ≈ tanh(z*0.7978)
        samples.append({"ratio": round(ratio, 4), "cdf": round(cdf, 6)})
    return samples


def _coerce_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


# DeFi acronyms that should stay uppercase after .title() — otherwise "raydium-amm"
# → "Raydium-Amm" and "deposit_lp" → "Deposit Lp" leak into user-facing copy.
_ACRONYMS = {"AMM", "CLMM", "DLMM", "LP", "DEX", "CL", "CP", "NFT",
             "V2", "V3", "V4", "USDC", "USDT", "DAI", "ETH", "SOL", "BNB", "BTC"}


def _humanize_token(tok: str) -> str:
    up = tok.upper()
    if up in _ACRONYMS:
        return up
    return tok.capitalize()


def humanize_protocol(name: str) -> str:
    """`raydium-amm` -> `Raydium AMM`, `uniswap-v3` -> `Uniswap V3`."""
    if not name:
        return ""
    return " ".join(_humanize_token(p) for p in name.replace("_", "-").split("-") if p)


def humanize_action(name: str) -> str:
    """`deposit_lp` -> `Deposit LP`, `prep_swap` -> `Prep Swap`."""
    if not name:
        return ""
    return " ".join(_humanize_token(p) for p in name.replace("-", "_").split("_") if p)


async def build_yield_execution_plan(
    ctx,
    *,
    chain: str,
    protocol: str,
    action: str,
    asset_in: str,
    amount_in: Any,
    asset_out: str | None = None,
    user_address: str | None = None,
    slippage_bps: int = 50,
    inventory: dict[str, Any] | None = None,
    research_thesis: str | None = None,
    extra: dict[str, Any] | None = None,
):
    if not user_address:
        wallet = getattr(ctx, "wallet", None)
        if wallet:
            user_address = str(wallet)
    # Wallet/chain compatibility preflight. Phantom in dual-mode exposes both
    # an EVM hex address and a Solana base58 pubkey; if the primary `wallet`
    # is wrong for the target chain but the per-chain ctx field has the
    # right one, swap it in here so we don't leak Enso 422 errors when the
    # user is asking from the wrong wallet (e.g. Phantom on Solana for an
    # Ethereum supply).
    import re as _re_addr
    def _is_evm_addr(s: Any) -> bool:
        return isinstance(s, str) and s.lower().startswith("0x") and len(s) == 42
    def _is_sol_addr(s: Any) -> bool:
        return isinstance(s, str) and bool(_re_addr.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", s))
    chain_norm = (chain or "").lower()
    is_evm_chain = chain_norm in {"ethereum", "polygon", "arbitrum", "base", "optimism", "bsc", "avalanche", "linea", "scroll", "zksync"}
    is_solana_chain = chain_norm in {"solana", "sol"}
    if is_evm_chain and not _is_evm_addr(user_address):
        evm_alt = getattr(ctx, "evm_wallet", None)
        if _is_evm_addr(evm_alt):
            user_address = evm_alt  # type: ignore[assignment]
    if is_solana_chain and not _is_sol_addr(user_address):
        sol_alt = getattr(ctx, "solana_wallet", None)
        if _is_sol_addr(sol_alt):
            user_address = sol_alt  # type: ignore[assignment]
    if not user_address:
        return err_envelope(
            "missing_wallet",
            "Connect a wallet before requesting an execution plan; the plan needs a destination address.",
        )
    # If the user's wallet still doesn't match the target chain, emit a
    # structured blocker instead of running the adapter (which would raise
    # an Enso 422 with a leaky URL in the detail).
    if is_evm_chain and not _is_evm_addr(user_address):
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=f"{humanize_protocol(protocol)} {asset_in} on {chain[:1].upper()+chain[1:]} requires an EVM wallet.",
        )
        plan.add_blocker(ExecutionBlocker(
            code="wallet_chain_mismatch",
            severity="blocker",
            title="Wrong wallet for this chain",
            detail=(
                f"This action runs on {chain} ({protocol} {asset_in}). Your connected wallet "
                f"`{str(user_address)[:12]}…` looks Solana (or otherwise non-EVM). "
                "Switch to an EVM wallet (MetaMask) and retry."
            ),
            affected_step_ids=[],
            cta="Connect an EVM wallet (MetaMask) to sign this action.",
        ))
        return ok_envelope(data={"plan": plan.to_dict()}, card_type="execution_plan_v3", card_payload=plan.to_dict())
    if is_solana_chain and not _is_sol_addr(user_address):
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=f"{humanize_protocol(protocol)} {asset_in} on Solana requires a Solana wallet.",
        )
        plan.add_blocker(ExecutionBlocker(
            code="wallet_chain_mismatch",
            severity="blocker",
            title="Wrong wallet for this chain",
            detail=(
                f"This action runs on Solana ({protocol} {asset_in}). Your connected wallet "
                f"`{str(user_address)[:12]}…` looks EVM (or otherwise non-Solana). "
                "Switch to a Solana wallet (Phantom in Solana mode) and retry."
            ),
            affected_step_ids=[],
            cta="Connect a Solana wallet (Phantom) to sign this action.",
        ))
        return ok_envelope(data={"plan": plan.to_dict()}, card_type="execution_plan_v3", card_payload=plan.to_dict())

    amount = _coerce_amount(amount_in)
    if amount <= 0:
        return err_envelope("invalid_amount", "amount_in must be a positive decimal value.")

    # Pool-link gate: when the (action, protocol, chain) tuple is on the
    # link-only list (V3 EVM LPs, generic V2 EVM LPs, non-Aave EVM supply,
    # non-LST stake), emit a pool_link card pointing at the exact pool on
    # the protocol app. Solana flows pass through (sidecar adapters handle
    # pair-aware prep + sim themselves).
    if is_pool_link_action(action=action, protocol=protocol, chain=chain):
        extra_dict = extra or {}
        url = pool_protocol_url(
            chain=chain,
            project=protocol,
            pool_address=extra_dict.get("pool_address") or extra_dict.get("poolAddress"),
            underlying_tokens=extra_dict.get("underlying_tokens") or extra_dict.get("underlyingTokens"),
            pool_symbol=extra_dict.get("pool_symbol") or extra_dict.get("poolSymbol"),
            project_url=extra_dict.get("project_url"),
        )
        kind_hint = classify_pool_kind(
            protocol=protocol,
            pool_symbol=extra_dict.get("pool_symbol") or asset_in,
            pool_id=extra_dict.get("pool_id"),
        )

        # V3 / CLMM pools get the interactive range card with live APR math.
        # Other pool types (V2, stable, vault) keep the bare pool_link redirect.
        if kind_hint == "v3":
            pool_symbol = extra_dict.get("pool_symbol") or asset_in or ""
            # Parse pair from pool_symbol when available, else default to USDC/<asset>.
            sym_parts = [s for s in pool_symbol.replace("/", "-").split("-") if s]
            t0 = sym_parts[0].upper() if len(sym_parts) >= 1 else (asset_in or "USDC").upper()
            t1 = sym_parts[1].upper() if len(sym_parts) >= 2 else "WETH"
            decimals_map = {"USDC": 6, "USDT": 6, "DAI": 18, "WETH": 18, "ETH": 18,
                             "WSOL": 9, "SOL": 9, "WBTC": 8, "BTC": 8, "BNB": 18}
            apy_pct = float(extra_dict.get("apy") or 0.0)
            current_price_hint = float(extra_dict.get("current_price") or 1.0)
            v3_card = {
                "card_type": "pool_deposit_v3",
                "card_id": f"v3-{protocol}-{(extra_dict.get('pool_id') or pool_symbol)[:24]}",
                "chain": chain,
                "protocol": protocol,
                "pool_address": extra_dict.get("pool_address") or extra_dict.get("poolAddress") or "",
                "pair": {
                    "token0": {"symbol": t0, "decimals": decimals_map.get(t0, 18), "address": None},
                    "token1": {"symbol": t1, "decimals": decimals_map.get(t1, 18), "address": None},
                },
                "current": {
                    "price_human": f"1 {t0} ≈ {current_price_hint:.4f} {t1}",
                    "current_price": current_price_hint,
                    "sqrt_price_x96": extra_dict.get("sqrt_price_x96"),
                    "tick": extra_dict.get("current_tick"),
                    "tvl_usd": extra_dict.get("tvl_usd"),
                    "vol_24h_usd": extra_dict.get("vol_24h_usd"),
                    "fee_tier_bps": extra_dict.get("fee_tier_bps"),
                    "tick_spacing": extra_dict.get("tick_spacing"),
                },
                "market": {
                    "base_apr_pct": apy_pct,
                    "reward_apr_pct": float(extra_dict.get("reward_apr") or 0.0),
                    "cdf_30d": extra_dict.get("cdf_30d") or [],
                },
                "input_token": {
                    "symbol": (asset_in or "USDC").upper(),
                    "decimals": decimals_map.get((asset_in or "USDC").upper(), 18),
                    "address": None,
                },
                "input_amount_human": str(amount),
                "input_amount_usd": float(amount),
                "initial_range": {"preset": "balanced", "lower_pct": -10.0, "upper_pct": 10.0},
                "initial_steps": [],
                "rebuild_endpoint": "/api/v1/pool/rebuild",
                "protocol_url": url,
                "finalize_externally": True,
                "notice": (
                    f"{protocol.title()} V3 concentrated liquidity — adjust the range to see "
                    "live APR / capital efficiency / in-range probability. Range NFT mint "
                    "currently finalizes on the protocol app (in-chat mint lands in Phase 4)."
                ),
            }
            return ok_envelope(data=v3_card, card_type="pool_deposit_v3", card_payload=v3_card)

        card = {
            "card_type": "pool_link",
            "title": f"{protocol.title()} · {action.replace('_', ' ').title()}",
            "protocol": protocol,
            "chain": chain,
            "pool_kind": kind_hint,
            "pool_symbol": extra_dict.get("pool_symbol") or asset_in,
            "pool_id": extra_dict.get("pool_id"),
            "pool_address": extra_dict.get("pool_address") or extra_dict.get("poolAddress"),
            "apy_pct": extra_dict.get("apy"),
            "tvl_usd": extra_dict.get("tvl_usd"),
            "underlying_tokens": extra_dict.get("underlying_tokens") or extra_dict.get("underlyingTokens"),
            "sentinel": extra_dict.get("sentinel") or {},
            "url": url,
            "amount": str(amount),
            "asset_in": asset_in,
            "amount_is_usd": bool(extra_dict.get("amount_is_usd")),
            "research_thesis": research_thesis,
            "exec_status": "link_only",
            "notice": (
                f"{protocol.title()} {kind_hint.upper()} pool — finalize on the "
                "protocol app. Direct execution from chat is currently disabled "
                "for this pool type because single-token Enso routing was silently "
                "depositing the wrong asset for many pools."
            ),
        }
        return ok_envelope(data=card, card_type="pool_link", card_payload=card)

    registry = build_default_registry()
    capability = registry.find(chain=chain, protocol=protocol, action=action)
    if not capability.supported:
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=f"Direct execution for {humanize_protocol(protocol)} {humanize_action(action)} on {chain[:1].upper()+chain[1:]} is not yet supported.",
        )
        plan.add_blocker(ExecutionBlocker(
            code="unsupported_adapter",
            severity="blocker",
            title="No verified adapter",
            detail=capability.reason or "No adapter is registered for that protocol/action/chain combination.",
            affected_step_ids=[],
            cta="Pick an adapter-supported protocol such as Aave V3 supply on Ethereum/Polygon/Arbitrum/Base.",
        ))
        return ok_envelope(
            data={"plan": plan.to_dict()},
            card_type="execution_plan_v3",
            card_payload=plan.to_dict(),
        )

    adapter = registry.adapter_for(chain=chain, protocol=protocol, action=action)
    assert adapter is not None  # registry.find succeeded above

    try:
        steps = await adapter.build(YieldBuildRequest(
            chain=chain,
            protocol=protocol,
            asset_in=asset_in,
            amount_in=amount,
            user_address=user_address,
            asset_out=asset_out,
            slippage_bps=slippage_bps,
            extra=extra,
        ))
    except ValueError as exc:
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=f"Could not build execution plan for {humanize_protocol(protocol)} {humanize_action(action)} on {chain[:1].upper()+chain[1:]}.",
        )
        plan.add_blocker(ExecutionBlocker(
            code="adapter_build_failed",
            severity="blocker",
            title="Adapter could not build steps",
            detail=str(exc),
            affected_step_ids=[],
            cta="Adjust the asset, chain, or amount and try again.",
        ))
        return ok_envelope(
            data={"plan": plan.to_dict()},
            card_type="execution_plan_v3",
            card_payload=plan.to_dict(),
        )

    proto_human = humanize_protocol(protocol)
    action_human = humanize_action(action)
    chain_human = (chain[:1].upper() + chain[1:]) if chain else chain
    plan = ExecutionPlanV3.new(
        title=f"{proto_human} {action_human}",
        summary=f"{action_human} {amount} {asset_in} via {proto_human} on {chain_human}.",
        research_thesis=research_thesis,
    )
    for step in steps:
        plan.add_step(step)

    if inventory:
        wallet_inventory = _inventory_from_dict(inventory)
        blockers = evaluate_preflight(steps=plan.steps, inventory=wallet_inventory)
        for blocker in blockers:
            plan.add_blocker(blocker)

    session_id = getattr(ctx, "session_id", None)
    if session_id:
        remember_strategy(StrategyRecord(
            session_id=str(session_id),
            chat_id=str(session_id),
            user_address=user_address,
            intent_summary=f"{action} {amount} {asset_in} via {protocol} on {chain}",
            plan=plan.to_dict(),
            constraints={
                "chain": chain,
                "protocol": protocol,
                "action": action,
                "asset_in": asset_in,
                "amount_in": str(amount),
                "asset_out": asset_out,
                "slippage_bps": slippage_bps,
            },
        ))

    # User-level wallet hold floor. When the plan's only signable step is a
    # half-zap prep_swap and the LP-add itself is link-only (Raydium / Orca /
    # Meteora handoff), totals.assets_required reflects only the swap leg —
    # so a user typing "$10 USDC" sees "USDC: 5" which is wrong. Surface the
    # FULL deposit amount as the wallet floor.
    try:
        floor_sym = (asset_in or "").strip().upper()
        if floor_sym and "+" not in floor_sym and not floor_sym.startswith("0X"):
            existing = plan.totals.assets_required.get(floor_sym)
            try:
                existing_v = float(existing) if existing else 0.0
            except (TypeError, ValueError):
                existing_v = 0.0
            req_v = float(amount) if amount else 0.0
            if req_v > existing_v:
                merged = dict(plan.totals.assets_required)
                text = f"{req_v:.8f}".rstrip("0").rstrip(".") or "0"
                merged[floor_sym] = text
                plan.totals.assets_required = merged
    except Exception:
        pass

    plan_dict = plan.to_dict()

    # CLMM-like protos: V3 EVM + Solana concentrated/dynamic. Attach a
    # range_block payload so the frontend can render the interactive range
    # slider above the step list (spec §6b).
    _V3_EVM_PROTOS = {
        "uniswap-v3", "uniswap-v4", "pancakeswap-v3", "pancake-v3",
        "aerodrome-slipstream", "aerodrome-cl",
    }
    _SOLANA_CLMM_LIKE_PROTOS = {
        "raydium-clmm", "raydium-amm-v3",
        "orca", "orca-whirlpools", "orca-clmm", "orca-dex",
        "meteora-dlmm", "meteora",
    }
    # Try Solana CLMM/DLMM first; emit range_block via sidecar pool_state probe.
    if chain.lower() in {"solana", "sol"} and protocol.lower() in _SOLANA_CLMM_LIKE_PROTOS:
        try:
            import os
            import aiohttp as _aiohttp
            sidecar_url = os.environ.get("SOLANA_YIELD_BUILDER_URL", "http://solana-yield-builder:8090")
            pair_sym = (extra or {}).get("pool_symbol") or asset_in or ""
            sides_sol = [p.strip().upper()
                         for p in pair_sym.replace("/", "-").split("-") if p.strip()]
            if len(sides_sol) >= 2:
                async with _aiohttp.ClientSession(timeout=_aiohttp.ClientTimeout(total=8)) as _sess:
                    async with _sess.post(
                        f"{sidecar_url}/pool_state",
                        json={"protocol": protocol, "pair": "-".join(sides_sol[:2])},
                    ) as _resp:
                        if _resp.status == 200:
                            sp = (await _resp.json()).get("pool") or {}
                            cur_price = float(sp.get("currentPrice") or 0.0)
                            kind = sp.get("kind") or "clmm"
                            tok_a = sp.get("tokenA") or {}
                            tok_b = sp.get("tokenB") or {}
                            plan_dict["range_block"] = {
                                "card_subtype": "v3_range",
                                "chain": chain,
                                "protocol": protocol,
                                "pool_address": sp.get("poolAddress"),
                                "pair": {
                                    "token0": {
                                        "symbol": tok_a.get("symbol") or sides_sol[0],
                                        "address": tok_a.get("mint") or "",
                                        "decimals": int(tok_a.get("decimals") or 9),
                                    },
                                    "token1": {
                                        "symbol": tok_b.get("symbol") or sides_sol[1],
                                        "address": tok_b.get("mint") or "",
                                        "decimals": int(tok_b.get("decimals") or 6),
                                    },
                                },
                                "current": {
                                    "current_price": cur_price,
                                    "price_human": (
                                        f"1 {tok_a.get('symbol') or sides_sol[0]} ≈ "
                                        f"{cur_price:.6f} {tok_b.get('symbol') or sides_sol[1]}"
                                    ),
                                    "tick": sp.get("tick"),
                                    "tick_spacing": sp.get("tickSpacing"),
                                    "bin_step": sp.get("binStep"),
                                    "fee_tier_bps": sp.get("feeBps"),
                                    "sqrt_price_x96": str(sp.get("sqrtPriceX64") or ""),
                                    "liquidity": str(sp.get("tvlUsd") or 0),
                                },
                                "market": {
                                    "base_apr_pct": float(sp.get("baseAprPct") or 0.0),
                                    "reward_apr_pct": float(sp.get("rewardAprPct") or 0.0),
                                    "cdf_30d": _synth_cdf_30d(sides_sol[0], sides_sol[1]),
                                    "kind": kind,
                                },
                                "initial_range": {
                                    "preset": "balanced",
                                    "lower_pct": -10.0,
                                    "upper_pct": 10.0,
                                },
                                "range_presets": [
                                    {"label": "Narrow", "lower_pct": -5.0, "upper_pct": 5.0},
                                    {"label": "Balanced", "lower_pct": -10.0, "upper_pct": 10.0},
                                    {"label": "Wide", "lower_pct": -25.0, "upper_pct": 25.0},
                                    {"label": "Full", "lower_pct": -50.0, "upper_pct": 100.0},
                                ],
                            }
        except Exception:
            pass
    if protocol.lower() in _V3_EVM_PROTOS:
        try:
            from src.data.v3_pool_resolver import resolve_v3_pool
            from src.data.asset_registry import resolve_any_evm_token
            from src.data.v3_tick_math import price_from_tick

            extra_dict = dict(extra or {})
            # If apy_base / apy_total wasn't pre-populated (direct-LP intent
            # skips the meta-fetch), look it up from DefiLlama yields for the
            # exact protocol + chain + symbol match so range_block.market
            # shows real APR instead of a stale 0.
            if not extra_dict.get("apy_base") and not extra_dict.get("apy_total"):
                try:
                    import aiohttp as _aiohttp
                    _ll_url = "https://yields.llama.fi/pools"
                    _pair_symbol_raw = (extra_dict.get("pool_symbol") or asset_in or "").upper().replace("/", "-")
                    _pair_target = _pair_symbol_raw
                    _pair_target_alt = "-".join(reversed(_pair_target.split("-")))
                    # DefiLlama chain canonicalization. "Optimism" → "op mainnet";
                    # "BSC" → "bsc"; "Polygon" → "polygon pos" sometimes; etc.
                    _DEFILLAMA_CHAIN_ALIASES = {
                        "optimism": ("op mainnet", "optimism"),
                        "polygon": ("polygon", "polygon pos", "matic"),
                        "bsc": ("bsc", "bnb smart chain", "binance"),
                        "avalanche": ("avalanche", "avax"),
                        "arbitrum": ("arbitrum", "arbitrum one"),
                        "ethereum": ("ethereum",),
                        "base": ("base",),
                        "linea": ("linea",),
                        "mantle": ("mantle",),
                        "zksync": ("zksync era", "zksync"),
                        "scroll": ("scroll",),
                    }
                    _chain_canonical = _DEFILLAMA_CHAIN_ALIASES.get(chain.lower(), (chain.lower(),))
                    async with _aiohttp.ClientSession(timeout=_aiohttp.ClientTimeout(total=6)) as _llsess:
                        async with _llsess.get(_ll_url) as _llresp:
                            if _llresp.status == 200:
                                _lldata = await _llresp.json()
                                _proto_l = protocol.lower()
                                best = None
                                best_tvl = 0.0
                                for _e in (_lldata.get("data") or []):
                                    if str(_e.get("project") or "").lower() != _proto_l:
                                        continue
                                    _ec = str(_e.get("chain") or "").lower()
                                    if not any(cv == _ec for cv in _chain_canonical):
                                        continue
                                    _sym = str(_e.get("symbol") or "").upper().replace("/", "-")
                                    if _pair_target not in _sym and _pair_target_alt not in _sym:
                                        continue
                                    _t = float(_e.get("tvlUsd") or 0)
                                    if _t > best_tvl:
                                        best = _e
                                        best_tvl = _t
                                if best is not None:
                                    extra_dict["apy_total"] = float(best.get("apy") or 0.0)
                                    extra_dict["apy_base"] = float(best.get("apyBase") or 0.0)
                                    extra_dict["apy_reward"] = float(best.get("apyReward") or 0.0)
                                    extra_dict["tvl_usd"] = float(best.get("tvlUsd") or 0.0)
                except Exception:
                    pass

            pair_sym = extra_dict.get("pool_symbol") or asset_in or ""
            fee_bps = int(extra_dict.get("fee_bps") or 500)
            sides = [p.strip().upper()
                     for p in pair_sym.replace("/", "-").split("-") if p.strip()]
            if len(sides) >= 2:
                meta_a = await resolve_any_evm_token(chain, sides[0])
                meta_b = await resolve_any_evm_token(chain, sides[1])
                # V3 pools always trade wrapped natives, never the 0xEee...
                # placeholder. Resolve the right wrapper per chain so the
                # range_block matches what the V3 NFT adapter actually mints
                # (WETH on EVM L1/L2, WBNB on BSC, WAVAX on Avalanche, WMATIC
                # on Polygon).
                from src.data.asset_registry import NATIVE_PLACEHOLDER
                _WRAP_BY_CHAIN = {
                    "ethereum": "WETH", "base": "WETH", "arbitrum": "WETH",
                    "optimism": "WETH", "linea": "WETH", "scroll": "WETH",
                    "zksync": "WETH", "bsc": "WBNB", "avalanche": "WAVAX",
                    "polygon": "WMATIC",
                }
                _wrap_sym = _WRAP_BY_CHAIN.get(chain.lower(), "WETH")
                _wrap_meta = await resolve_any_evm_token(chain, _wrap_sym)
                if meta_a and meta_a[0] == NATIVE_PLACEHOLDER and _wrap_meta:
                    meta_a = _wrap_meta
                    sides[0] = _wrap_sym
                if meta_b and meta_b[0] == NATIVE_PLACEHOLDER and _wrap_meta:
                    meta_b = _wrap_meta
                    sides[1] = _wrap_sym
                if meta_a and meta_b:
                    pool_state = await resolve_v3_pool(
                        chain=chain, protocol=protocol,
                        token_a=meta_a[0], token_b=meta_b[0], fee_bps=fee_bps,
                    )
                    if pool_state is None:
                        # Match the V3 NFT adapter's fee-tier auto-discovery:
                        # the user-given tier might not exist; pick the deepest
                        # tier that does, so the slider always renders.
                        from src.data.v3_pool_resolver import list_fee_tiers_with_pools
                        try:
                            tiers = await list_fee_tiers_with_pools(
                                chain=chain, protocol=protocol,
                                token_a=meta_a[0], token_b=meta_b[0],
                            )
                        except Exception:
                            tiers = []
                        if tiers:
                            best_state = max(tiers, key=lambda t: int(getattr(t, "liquidity", 0) or 0))
                            pool_state = best_state
                            fee_bps = best_state.fee_bps
                    if pool_state is not None:
                        # price_from_tick expects POOL token0/token1 decimals
                        # AND returns token1-per-token0. The user's sides[0] /
                        # sides[1] may be in the opposite order from the pool's
                        # on-chain token0/token1 (addresses sort the pool, the
                        # user types whichever side first). Resolve both
                        # decimals + direction by comparing addresses.
                        pool_t0_addr = (pool_state.token0 or "").lower()
                        user_a_addr = (meta_a[0] or "").lower()
                        user_b_addr = (meta_b[0] or "").lower()
                        if pool_t0_addr == user_a_addr:
                            dec0, dec1 = meta_a[1], meta_b[1]
                            invert = False
                        elif pool_t0_addr == user_b_addr:
                            dec0, dec1 = meta_b[1], meta_a[1]
                            invert = True
                        else:
                            # Unknown ordering — fall back to user order and
                            # accept that the display might be flipped (rare).
                            dec0, dec1 = meta_a[1], meta_b[1]
                            invert = False
                        raw = price_from_tick(pool_state.tick, dec0, dec1)
                        if invert:
                            from decimal import Decimal as _D
                            raw = _D(1) / raw if raw != 0 else raw
                        human_price = float(raw)
                        plan_dict["range_block"] = {
                            "card_subtype": "v3_range",
                            "chain": chain,
                            "protocol": protocol,
                            "pool_address": pool_state.pool_address,
                            "pair": {
                                "token0": {"symbol": sides[0],
                                           "address": pool_state.token0,
                                           "decimals": meta_a[1]},
                                "token1": {"symbol": sides[1],
                                           "address": pool_state.token1,
                                           "decimals": meta_b[1]},
                            },
                            "current": {
                                "current_price": human_price,
                                "price_human": f"1 {sides[0]} ≈ {human_price:.6f} {sides[1]}",
                                "tick": pool_state.tick,
                                "tick_spacing": pool_state.tick_spacing,
                                "fee_tier_bps": pool_state.fee_bps,
                                "sqrt_price_x96": str(pool_state.sqrt_price_x96),
                                "liquidity": str(pool_state.liquidity),
                            },
                            "market": {
                                "base_apr_pct": float(extra_dict.get("apy_base") or extra_dict.get("apy_total") or 0.0),
                                "reward_apr_pct": float(extra_dict.get("apy_reward") or 0.0),
                                "tvl_usd": float(extra_dict.get("tvl_usd") or 0.0),
                                "cdf_30d": _synth_cdf_30d(sides[0], sides[1]),
                                "kind": "v3" if "v3" in protocol.lower() else (
                                    "v4" if "v4" in protocol.lower() else (
                                        "slipstream" if "slipstream" in protocol.lower() else "v3"
                                    )
                                ),
                            },
                            "initial_range": {
                                "preset": "balanced",
                                "lower_pct": -10.0,
                                "upper_pct": 10.0,
                            },
                            # Frontend slider bounds: lower in [-50, 0], upper in [0, 100].
                            # Anything wider would clip silently and confuse the user.
                            "range_presets": [
                                {"label": "Narrow", "lower_pct": -5.0, "upper_pct": 5.0},
                                {"label": "Balanced", "lower_pct": -10.0, "upper_pct": 10.0},
                                {"label": "Wide", "lower_pct": -25.0, "upper_pct": 25.0},
                                {"label": "Full", "lower_pct": -50.0, "upper_pct": 100.0},
                            ],
                        }
        except Exception:
            pass

    return ok_envelope(
        data={"plan": plan_dict, "adapter_id": capability.adapter_id},
        card_type="execution_plan_v3",
        card_payload=plan_dict,
    )


def _inventory_from_dict(raw: dict[str, Any]) -> WalletInventory:
    balances = {}
    for entry in raw.get("balances") or []:
        try:
            chain = str(entry["chain"]).lower()
            asset = str(entry["asset"]).upper()
            amount = Decimal(str(entry.get("amount", 0)))
            balances[(chain, asset)] = amount
        except (KeyError, InvalidOperation, TypeError):
            continue
    native_gas = {}
    for entry in raw.get("native_gas") or []:
        try:
            chain = str(entry["chain"]).lower()
            amount = Decimal(str(entry.get("amount", 0)))
            native_gas[chain] = amount
        except (KeyError, InvalidOperation, TypeError):
            continue
    allowances = {}
    for entry in raw.get("allowances") or []:
        try:
            chain = str(entry["chain"]).lower()
            asset = str(entry["asset"]).upper()
            spender = str(entry["spender"]).lower()
            amount = Decimal(str(entry.get("amount", 0)))
            allowances[(chain, asset, spender)] = amount
        except (KeyError, InvalidOperation, TypeError):
            continue
    return WalletInventory(
        evm_address=raw.get("evm_address"),
        solana_address=raw.get("solana_address"),
        chain_id=raw.get("chain_id"),
        balances=balances,
        native_gas=native_gas,
        allowances=allowances,
    )
