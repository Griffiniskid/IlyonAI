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


def _coerce_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


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
    if not user_address:
        return err_envelope(
            "missing_wallet",
            "Connect a wallet before requesting an execution plan; the plan needs a destination address.",
        )

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
            title=f"{protocol} {action}",
            summary=f"Direct execution for {protocol} {action} on {chain} is not yet supported.",
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
            title=f"{protocol} {action}",
            summary=f"Could not build execution plan for {protocol} {action} on {chain}.",
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

    plan = ExecutionPlanV3.new(
        title=f"{protocol.title()} {action.replace('_', ' ').title()}",
        summary=f"{action.replace('_', ' ').title()} {amount} {asset_in} via {protocol} on {chain}.",
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

    plan_dict = plan.to_dict()

    # V3 EVM: attach a range_block payload so the frontend can render the
    # interactive range slider above the step list. Restores the slider lost
    # when V3 NFT native execution replaced the pool_deposit_v3 redirect card.
    _V3_EVM_PROTOS = {
        "uniswap-v3", "uniswap-v4", "pancakeswap-v3", "pancake-v3",
        "aerodrome-slipstream", "aerodrome-cl",
    }
    if protocol.lower() in _V3_EVM_PROTOS:
        try:
            from src.data.v3_pool_resolver import resolve_v3_pool
            from src.data.asset_registry import resolve_any_evm_token
            from src.data.v3_tick_math import price_from_tick

            extra_dict = extra or {}
            pair_sym = extra_dict.get("pool_symbol") or asset_in or ""
            fee_bps = int(extra_dict.get("fee_bps") or 500)
            sides = [p.strip().upper()
                     for p in pair_sym.replace("/", "-").split("-") if p.strip()]
            if len(sides) >= 2:
                meta_a = await resolve_any_evm_token(chain, sides[0])
                meta_b = await resolve_any_evm_token(chain, sides[1])
                if meta_a and meta_b:
                    pool_state = await resolve_v3_pool(
                        chain=chain, protocol=protocol,
                        token_a=meta_a[0], token_b=meta_b[0], fee_bps=fee_bps,
                    )
                    if pool_state is not None:
                        human_price = float(price_from_tick(
                            pool_state.tick, meta_a[1], meta_b[1]
                        ))
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
                                "base_apr_pct": 0.0,
                                "reward_apr_pct": 0.0,
                                "cdf_30d": [],
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
                                {"label": "Full", "lower_pct": -100.0, "upper_pct": 10000.0},
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
