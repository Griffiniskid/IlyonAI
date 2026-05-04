"""build_yield_strategy_plan — chain prerequisite swap/bridge into a yield deposit.

This is the composer behind prompts like:
- "bridge 500 USDC from Ethereum to Base then supply to Aave V3"
- "swap 1 ETH to USDC and deposit to Aave"
- "deposit 100 USDC and bridge to Arbitrum first if needed"

Emits ONE ExecutionPlanV3 with prerequisite step(s) + approve + supply, all
dependency-linked so the V3 card only enables the next ready step.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from src.agent.tools._base import err_envelope, ok_envelope
from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.capabilities import build_default_registry
from src.defi.execution.models import (
    ExecutionPlanV3,
    UnsignedStepTransaction,
    make_step,
)
from src.defi.strategy.memory import StrategyRecord, remember_strategy


_CHAIN_IDS = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
    "bsc": 56,
}


def _coerce(amount: Any) -> Decimal:
    try:
        return Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


async def build_yield_strategy_plan(
    ctx,
    *,
    deposit_chain: str,
    deposit_protocol: str,
    deposit_action: str,
    deposit_asset: str,
    deposit_amount: Any,
    user_address: str | None = None,
    source_chain: str | None = None,
    source_asset: str | None = None,
    source_amount: Any = None,
    research_thesis: str | None = None,
    slippage_bps: int = 50,
):
    """Compose prerequisite swap/bridge with the actual yield deposit.

    Required: deposit_chain/protocol/action/asset/amount.
    Optional prerequisites:
      - source_asset != deposit_asset (same chain): emits a swap prerequisite
      - source_chain != deposit_chain: emits a bridge prerequisite
    """
    if not user_address:
        wallet = getattr(ctx, "wallet", None)
        if wallet:
            user_address = str(wallet)
    if not user_address:
        return err_envelope("missing_wallet", "Connect a wallet before composing a strategy plan.")

    deposit_amount_dec = _coerce(deposit_amount)
    if deposit_amount_dec <= 0:
        return err_envelope("invalid_amount", "deposit_amount must be > 0.")

    registry = build_default_registry()
    capability = registry.find(chain=deposit_chain, protocol=deposit_protocol, action=deposit_action)
    if not capability.supported:
        plan = ExecutionPlanV3.new(
            title=f"{deposit_protocol} {deposit_action}",
            summary=f"Direct execution for {deposit_protocol} {deposit_action} on {deposit_chain} is not supported yet.",
        )
        from src.defi.execution.models import ExecutionBlocker
        plan.add_blocker(ExecutionBlocker(
            code="unsupported_adapter",
            severity="blocker",
            title="No verified adapter",
            detail=capability.reason or "Unsupported adapter combination.",
            affected_step_ids=[],
        ))
        return ok_envelope(data={"plan": plan.to_dict()}, card_type="execution_plan_v3", card_payload=plan.to_dict())

    adapter = registry.adapter_for(chain=deposit_chain, protocol=deposit_protocol, action=deposit_action)
    assert adapter is not None
    deposit_steps = await adapter.build(YieldBuildRequest(
        chain=deposit_chain,
        protocol=deposit_protocol,
        asset_in=deposit_asset,
        amount_in=deposit_amount_dec,
        user_address=user_address,
        slippage_bps=slippage_bps,
    ))
    if not deposit_steps:
        return err_envelope("adapter_returned_no_steps", "Adapter returned no steps for this deposit.")

    prerequisite_steps: list = []
    next_index = 1

    if source_chain and source_chain.lower() != deposit_chain.lower():
        bridge_amount = _coerce(source_amount) or deposit_amount_dec
        bridge_step = make_step(
            index=next_index,
            action="bridge",
            title=f"Bridge {bridge_amount} {source_asset or deposit_asset} from {source_chain} to {deposit_chain}",
            description=(
                f"Bridge prerequisite via deBridge so you have {deposit_asset} on {deposit_chain} for the deposit."
            ),
            chain=source_chain,
            wallet="MetaMask",
            protocol="deBridge",
            asset_in=source_asset or deposit_asset,
            amount_in=str(bridge_amount),
            asset_out=deposit_asset,
            slippage_bps=slippage_bps,
            gas_estimate_usd=3.5,
            duration_estimate_s=120,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=_CHAIN_IDS.get(source_chain.lower()),
                serialized=f"deBridge://{source_chain}->{deposit_chain}/{source_asset or deposit_asset}/{bridge_amount}",
            ),
            risk_warnings=[
                "Cross-chain bridges introduce additional smart-contract surface; verify the destination address before signing.",
            ],
            blocker_codes=["adapter_quote_required"],
        )
        prerequisite_steps.append(bridge_step)
        next_index += 1

    if source_asset and source_chain == deposit_chain and source_asset.upper() != deposit_asset.upper():
        swap_amount = _coerce(source_amount) or deposit_amount_dec
        swap_step = make_step(
            index=next_index,
            action="swap",
            title=f"Swap {swap_amount} {source_asset} → {deposit_asset} on {deposit_chain}",
            description=(
                f"Swap prerequisite so you have {deposit_asset} on {deposit_chain} for the deposit."
            ),
            chain=deposit_chain,
            wallet="MetaMask" if deposit_chain.lower() != "solana" else "Phantom",
            protocol="enso" if deposit_chain.lower() != "solana" else "jupiter",
            asset_in=source_asset,
            amount_in=str(swap_amount),
            asset_out=deposit_asset,
            slippage_bps=slippage_bps,
            gas_estimate_usd=2.5,
            duration_estimate_s=20,
            transaction=UnsignedStepTransaction(
                chain_kind="evm" if deposit_chain.lower() != "solana" else "solana",
                chain_id=_CHAIN_IDS.get(deposit_chain.lower()),
                serialized=f"router://{deposit_chain}/{source_asset}/{deposit_asset}/{swap_amount}",
            ),
            risk_warnings=[
                f"Quote refreshes near sign time; price may move within {slippage_bps/100:.2f}% slippage.",
            ],
            blocker_codes=["adapter_quote_required"],
        )
        prerequisite_steps.append(swap_step)
        next_index += 1

    # Re-stamp deposit step indices, remap internal depends_on to new ids,
    # and chain the first deposit step off the last prerequisite.
    id_map: dict[str, str] = {}
    rebased_deposit_steps = []
    for ordinal, step in enumerate(deposit_steps):
        old_id = step.step_id
        new_id = f"step_{uuid4().hex[:10]}"
        id_map[old_id] = new_id
        step.step_id = new_id
        step.index = next_index
        # Remap internal deps to the new step ids issued so far.
        step.depends_on = [id_map.get(dep, dep) for dep in step.depends_on]
        # First deposit step also depends on the last prerequisite (bridge / swap).
        if ordinal == 0 and prerequisite_steps:
            last_prereq_id = prerequisite_steps[-1].step_id
            if last_prereq_id not in step.depends_on:
                step.depends_on = [last_prereq_id, *step.depends_on]
        rebased_deposit_steps.append(step)
        next_index += 1

    plan = ExecutionPlanV3.new(
        title=f"{deposit_protocol.title()} Strategy",
        summary=(
            (research_thesis or
             f"Bridge / swap into {deposit_asset} on {deposit_chain}, then "
             f"{deposit_action} {deposit_amount_dec} {deposit_asset} via {deposit_protocol}.")
        ),
        research_thesis=research_thesis,
    )
    for step in [*prerequisite_steps, *rebased_deposit_steps]:
        plan.add_step(step)

    session_id = getattr(ctx, "session_id", None)
    if session_id:
        remember_strategy(StrategyRecord(
            session_id=str(session_id),
            chat_id=str(session_id),
            user_address=user_address,
            intent_summary=(
                f"{deposit_action} {deposit_amount_dec} {deposit_asset} via {deposit_protocol} on {deposit_chain}"
                + (f" (after bridge from {source_chain})" if source_chain and source_chain.lower() != deposit_chain.lower() else "")
                + (f" (after swap {source_asset}→{deposit_asset})" if source_asset and source_asset.upper() != deposit_asset.upper() else "")
            ),
            plan=plan.to_dict(),
            constraints={
                "deposit_chain": deposit_chain,
                "deposit_protocol": deposit_protocol,
                "deposit_action": deposit_action,
                "deposit_asset": deposit_asset,
                "deposit_amount": str(deposit_amount_dec),
                "source_chain": source_chain,
                "source_asset": source_asset,
                "source_amount": str(_coerce(source_amount)) if source_amount else None,
                "slippage_bps": slippage_bps,
            },
        ))

    return ok_envelope(
        data={"plan": plan.to_dict(), "adapter_id": capability.adapter_id, "prerequisite_steps": len(prerequisite_steps)},
        card_type="execution_plan_v3",
        card_payload=plan.to_dict(),
    )
