"""F03 INSUFFICIENT_BALANCE preflight pin tests.

Confirms build_yield_execution_plan attaches a real INSUFFICIENT_BALANCE
blocker when the wallet's balance for the required asset is below the
plan's totals.assets_required. Pass-N hand-read confirmed the earlier
build emitted a `ready` plan with empty wallet + 100k USDC supply intent;
this test pins the fix so it can't regress silently.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest

from IlyonAi_Wallet_assistant_main.server.app.agents import crypto_agent

from src.agent.tools._base import ToolCtx
# Import the submodule explicitly via importlib so monkeypatch can rebind the
# `build_default_registry` symbol the function looks up at call time. A
# straight `import src.agent.tools.build_yield_execution_plan as bye_mod`
# resolves to the function (re-exported via tools/__init__.py), not the
# module — Python's import system rebinds the attribute on the parent.
import importlib
bye_mod = importlib.import_module(
    "src.agent.tools.build_yield_execution_plan"
)
build_yield_execution_plan = bye_mod.build_yield_execution_plan
from src.defi.execution.adapters.base import (
    CapabilityResult,
    YieldBuildRequest,
)
from src.defi.execution.capabilities import AdapterRegistry
from src.defi.execution.models import ExecutionStepV3


class _FakeAdapter:
    """Minimal YieldAdapter — returns one supply step with a real asset_in."""
    adapter_id = "fake-test-adapter"
    chains = {"ethereum"}
    protocols = {"aave-v3"}
    actions = {"supply"}

    def supports(self, *, chain, protocol, action):
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request):  # pragma: no cover — not exercised
        raise NotImplementedError

    async def build(self, request: YieldBuildRequest):
        return [
            ExecutionStepV3(
                step_id="step_fake_supply",
                index=1,
                action="supply",
                title="Aave V3 supply",
                description="Supply USDC into Aave V3.",
                chain="ethereum",
                wallet="MetaMask",
                protocol="aave-v3",
                asset_in="USDC",
                amount_in=str(request.amount_in),
                gas_estimate_usd=3.0,
                duration_estimate_s=30,
            ),
        ]

    async def verify(self, request):  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
def ctx():
    return ToolCtx(
        services=type("S", (), {})(),
        user_id=1,
        wallet="0x0000000000000000000000000000000000000abc",
        evm_wallet="0x0000000000000000000000000000000000000abc",
    )


@pytest.mark.asyncio
async def test_empty_wallet_emits_insufficient_balance_blocker(monkeypatch, ctx):
    """Empty wallet + 100k USDC supply → INSUFFICIENT_BALANCE blocker."""
    # Zero balance — wallet has no USDC and no ETH for gas.
    fake_zero_balance = json.dumps({
        "type": "balance_report",
        "wallet_addresses": ["0x0000000000000000000000000000000000000abc"],
        "balances": [
            {
                "chain": "Ethereum",
                "native_symbol": "ETH",
                "native_balance": 0.0,
                "native_usd": 0.0,
                "tokens": [],
                "usd_total": 0.0,
            },
        ],
        "total_usd": 0.0,
    })

    monkeypatch.setattr(
        crypto_agent,
        "get_smart_wallet_balance",
        lambda addr, user_address="", solana_address="": fake_zero_balance,
        raising=True,
    )
    # Swap in a tame registry so we don't hit the real Enso adapter.
    monkeypatch.setattr(
        bye_mod,
        "build_default_registry",
        lambda: AdapterRegistry(adapters=[_FakeAdapter()]),
    )

    env = await build_yield_execution_plan(
        ctx,
        chain="ethereum",
        protocol="aave-v3",
        action="supply",
        asset_in="USDC",
        amount_in="100000",
        user_address="0x0000000000000000000000000000000000000abc",
    )

    assert env.ok is True, f"envelope must be ok, got error: {env.error}"
    plan = env.data["plan"]
    blocker_codes = [b["code"] for b in plan.get("blockers", [])]
    assert "INSUFFICIENT_BALANCE" in blocker_codes, (
        f"expected INSUFFICIENT_BALANCE blocker, got: {blocker_codes}"
    )
    # The blocker detail must name the shortfall amount + token so the
    # frontend recovery card has something concrete to surface.
    usdc_blocker = next(
        b for b in plan["blockers"]
        if b["code"] == "INSUFFICIENT_BALANCE" and "USDC" in b.get("detail", "")
    )
    assert "100000" in usdc_blocker["detail"] or "100,000" in usdc_blocker["detail"] \
        or "1e+05" in usdc_blocker["detail"]
    assert usdc_blocker["severity"] == "blocker"
    # GAS_TOPUP_REQUIRED should also fire — supply step has gas_estimate_usd=3.0
    # and wallet has 0 ETH. (V7-063 — UPPER_SNAKE canonical token.)
    assert "GAS_TOPUP_REQUIRED" in blocker_codes


@pytest.mark.asyncio
async def test_balance_lookup_failure_preserves_ready_plan(monkeypatch, ctx):
    """Fail-soft contract: balance scanner exception keeps the original plan."""
    def _raise(*_a, **_kw):
        raise RuntimeError("scanner unreachable")

    monkeypatch.setattr(
        crypto_agent,
        "get_smart_wallet_balance",
        _raise,
        raising=True,
    )
    monkeypatch.setattr(
        bye_mod,
        "build_default_registry",
        lambda: AdapterRegistry(adapters=[_FakeAdapter()]),
    )

    env = await build_yield_execution_plan(
        ctx,
        chain="ethereum",
        protocol="aave-v3",
        action="supply",
        asset_in="USDC",
        amount_in="100",
        user_address="0x0000000000000000000000000000000000000abc",
    )

    assert env.ok is True
    plan = env.data["plan"]
    # No balance-related blockers — preflight failed soft.
    blocker_codes = [b["code"] for b in plan.get("blockers", [])]
    assert "INSUFFICIENT_BALANCE" not in blocker_codes
    assert "GAS_TOPUP_REQUIRED" not in blocker_codes
