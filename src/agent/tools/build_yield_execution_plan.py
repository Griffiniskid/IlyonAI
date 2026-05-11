"""Build a real ExecutionPlanV3 for a specific yield action through registry adapters."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from src.agent.protocol_urls import is_pool_link_action, pool_protocol_url
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
        kind_hint = "v3" if any(k in protocol.lower() for k in ("v3", "clmm", "slipstream")) else (
            "stable" if any(k in protocol.lower() for k in ("curve", "balancer", "saddle")) else (
                "vault" if any(k in protocol.lower() for k in ("yearn", "morpho", "spark", "beefy", "gamma", "arrakis")) else "v2"
            )
        )
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

    return ok_envelope(
        data={"plan": plan.to_dict(), "adapter_id": capability.adapter_id},
        card_type="execution_plan_v3",
        card_payload=plan.to_dict(),
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
