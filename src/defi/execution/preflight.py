"""Wallet preflight: verify balance, gas, allowance, wallet kind before signing."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from src.defi.execution.models import ExecutionBlocker, ExecutionStepV3


@dataclass
class WalletInventory:
    evm_address: str | None = None
    solana_address: str | None = None
    chain_id: int | None = None
    balances: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    native_gas: dict[str, Decimal] = field(default_factory=dict)
    allowances: dict[tuple[str, str, str], Decimal] = field(default_factory=dict)
    existing_positions: list[dict[str, Any]] = field(default_factory=list)

    def balance_of(self, chain: str, asset: str) -> Decimal:
        return self.balances.get((chain.lower(), asset.upper()), Decimal(0))

    def gas_balance(self, chain: str) -> Decimal:
        return self.native_gas.get(chain.lower(), Decimal(0))

    def allowance_for(self, chain: str, asset: str, spender: str) -> Decimal:
        return self.allowances.get((chain.lower(), asset.upper(), spender.lower()), Decimal(0))


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(0)


def _wallet_for_chain(chain_kind: str, inventory: WalletInventory) -> str | None:
    if chain_kind == "solana":
        return inventory.solana_address
    return inventory.evm_address


def _chain_kind(chain: str) -> str:
    return "solana" if chain.lower() in {"solana", "sol"} else "evm"


def evaluate_preflight(
    *,
    steps: Iterable[ExecutionStepV3],
    inventory: WalletInventory,
    min_native_gas: dict[str, float] | None = None,
) -> list[ExecutionBlocker]:
    """Inspect each step against wallet inventory and return blockers.

    Blockers are the only place execution_plan_v3 says "do not sign yet". A
    step that gets a blocker here will be marked `blocked` by the plan.
    """
    blockers: list[ExecutionBlocker] = []
    min_native_gas = min_native_gas or {"ethereum": 0.005, "base": 0.001, "arbitrum": 0.001, "optimism": 0.001, "polygon": 1.0, "bsc": 0.005, "solana": 0.01}
    seen_codes: set[str] = set()

    for step in steps:
        kind = _chain_kind(step.chain)
        wallet_address = _wallet_for_chain(kind, inventory)
        step_chain = step.chain.lower()

        if wallet_address is None:
            code = f"missing_{kind}_wallet"
            if code not in seen_codes:
                blockers.append(ExecutionBlocker(
                    code=code,
                    severity="blocker",
                    title=f"Connect a {kind.upper()} wallet",
                    detail=(
                        f"Step {step.index} ({step.title}) requires a {kind} wallet but none is connected."
                    ),
                    affected_step_ids=[step.step_id],
                    cta=("Connect Phantom for Solana." if kind == "solana" else "Connect MetaMask or another EVM wallet."),
                ))
                seen_codes.add(code)
            continue

        if step.action in {"approve", "swap", "supply", "stake", "deposit_lp", "bridge", "withdraw"}:
            if step.asset_in and step.amount_in:
                amount = _to_decimal(step.amount_in)
                balance = inventory.balance_of(step_chain, step.asset_in)
                if amount > 0 and balance < amount:
                    blockers.append(ExecutionBlocker(
                        code="insufficient_balance",
                        severity="blocker",
                        title=f"Insufficient {step.asset_in} on {step.chain}",
                        detail=(
                            f"Step {step.index} needs {amount} {step.asset_in} on {step.chain}; "
                            f"wallet currently holds {balance}. Top up before signing."
                        ),
                        affected_step_ids=[step.step_id],
                        cta=f"Bridge or swap into {step.asset_in} on {step.chain} before retrying.",
                    ))

        if step.action != "wait_receipt" and step.action != "verify_balance":
            min_required = Decimal(str(min_native_gas.get(step_chain, 0.0)))
            if min_required > 0:
                gas_balance = inventory.gas_balance(step_chain)
                if gas_balance < min_required:
                    blockers.append(ExecutionBlocker(
                        code="insufficient_gas",
                        severity="blocker",
                        title=f"Insufficient native gas on {step.chain}",
                        detail=(
                            f"Step {step.index} requires roughly {min_required} native gas on {step.chain}; "
                            f"wallet has {gas_balance}."
                        ),
                        affected_step_ids=[step.step_id],
                        cta=f"Send some native {step.chain} gas to the connected wallet.",
                    ))

        if step.action in {"swap", "supply", "stake", "deposit_lp"} and step.asset_in and step.amount_in:
            spender = step.transaction.spender if step.transaction and step.transaction.spender else None
            if spender:
                allowance = inventory.allowance_for(step_chain, step.asset_in, spender)
                amount = _to_decimal(step.amount_in)
                if allowance < amount:
                    # Allowance shortfall is only a blocker when the prior
                    # approve step is not part of the plan.
                    has_approve = any(
                        prior.action == "approve" and prior.asset_in == step.asset_in
                        for prior in steps
                        if prior.index < step.index
                    )
                    if not has_approve:
                        blockers.append(ExecutionBlocker(
                            code="missing_allowance",
                            severity="blocker",
                            title=f"Missing approval for {step.asset_in}",
                            detail=(
                                f"Step {step.index} needs allowance >= {amount} for spender {spender} but current allowance is {allowance}."
                            ),
                            affected_step_ids=[step.step_id],
                            cta="Add an explicit approve step to the plan or grant allowance manually.",
                        ))

    return blockers
