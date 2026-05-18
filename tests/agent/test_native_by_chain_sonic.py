"""V7-069 — Sonic native gas pin tests.

Pins two contracts:
  1. `_NATIVE_BY_CHAIN["sonic"] == "S"` — Sonic L1 gas symbol is "S" (the
     rebranded FTM token). Without this entry the gas preflight silently
     skips Sonic plans and exposes a sign button on a plan the user can't
     actually broadcast.
  2. `build_yield_execution_plan` emits a GAS_TOPUP_REQUIRED blocker
     carrying token "S" when a Sonic plan has gas estimates but the wallet
     has zero S.
"""
from __future__ import annotations

import importlib
import json

import pytest

from IlyonAi_Wallet_assistant_main.server.app.agents import crypto_agent

from src.agent.tools._base import ToolCtx

bye_mod = importlib.import_module("src.agent.tools.build_yield_execution_plan")
build_yield_execution_plan = bye_mod.build_yield_execution_plan

from src.defi.execution.adapters.base import (
    CapabilityResult,
    YieldBuildRequest,
)
from src.defi.execution.capabilities import AdapterRegistry
from src.defi.execution.models import ExecutionStepV3


class _FakeSonicAdapter:
    """Minimal YieldAdapter that returns one supply step on Sonic with a
    real gas estimate so the preflight's gas-top-up math has something to
    compute against. Uses aave-v3 protocol so the runtime takes the
    SUPPLY_EXEC_PROTOCOLS executable branch (not the pool_link link-only
    redirect) and the F03/F08 wallet preflight actually runs."""
    adapter_id = "fake-sonic-adapter"
    chains = {"sonic"}
    protocols = {"aave-v3"}
    actions = {"supply"}

    def supports(self, *, chain, protocol, action):
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request):  # pragma: no cover
        raise NotImplementedError

    async def build(self, request: YieldBuildRequest):
        return [
            ExecutionStepV3(
                step_id="step_fake_sonic_supply",
                index=1,
                action="supply",
                title="Aave V3 supply",
                description="Supply USDC into Aave V3 on Sonic.",
                chain="sonic",
                wallet="MetaMask",
                protocol="aave-v3",
                asset_in="USDC",
                amount_in=str(request.amount_in),
                gas_estimate_usd=2.0,  # ~ 6.67 S at $0.30 with 1.5× headroom
                duration_estimate_s=30,
            ),
        ]

    async def verify(self, request):  # pragma: no cover
        raise NotImplementedError


def test_native_by_chain_contains_sonic_s():
    """Source-level pin: `_NATIVE_BY_CHAIN["sonic"]` must equal `"S"`.

    Read the symbol out of the function source rather than re-executing the
    function — the dict lives inside the build_yield_execution_plan body and
    is not exported. This pin guards against accidental rename/removal.
    """
    src = bye_mod.__file__
    with open(src, "r", encoding="utf-8") as f:
        body = f.read()
    # The two acceptable literal forms in the dict, both must appear at
    # least once together in the same dict body.
    assert ('"sonic": "S"' in body) or ("'sonic': 'S'" in body), (
        "V7-069 — _NATIVE_BY_CHAIN must map 'sonic' → 'S' so the gas-top-up "
        "preflight applies to Sonic plans."
    )


@pytest.fixture
def ctx():
    return ToolCtx(
        services=type("S", (), {})(),
        user_id=1,
        wallet="0x0000000000000000000000000000000000000abc",
        evm_wallet="0x0000000000000000000000000000000000000abc",
    )


@pytest.mark.asyncio
async def test_sonic_gas_exhausted_emits_blocker_with_s_token(monkeypatch, ctx):
    """Wallet with USDC but zero S on Sonic + non-zero step gas_estimate_usd
    → GAS_TOP_UP blocker that names the S token."""
    fake_balance = json.dumps({
        "type": "balance_report",
        "wallet_addresses": ["0x0000000000000000000000000000000000000abc"],
        "balances": [
            {
                "chain": "Sonic",
                "native_symbol": "S",
                "native_balance": 0.0,
                "native_usd": 0.0,
                "tokens": [
                    {
                        "symbol": "USDC",
                        "balance": 1_000_000.0,
                        "usd_value": 1_000_000.0,
                    },
                ],
                "usd_total": 1_000_000.0,
            },
        ],
        "total_usd": 1_000_000.0,
    })

    monkeypatch.setattr(
        crypto_agent,
        "get_smart_wallet_balance",
        lambda addr, user_address="", solana_address="": fake_balance,
        raising=True,
    )
    monkeypatch.setattr(
        bye_mod,
        "build_default_registry",
        lambda: AdapterRegistry(adapters=[_FakeSonicAdapter()]),
    )

    env = await build_yield_execution_plan(
        ctx,
        chain="sonic",
        protocol="aave-v3",
        action="supply",
        asset_in="USDC",
        amount_in="100",
        user_address="0x0000000000000000000000000000000000000abc",
    )

    assert env.ok is True, f"envelope must be ok, got error: {env.error}"
    plan = env.data["plan"]
    blockers = plan.get("blockers", [])
    blocker_codes = [b["code"] for b in blockers]
    assert "GAS_TOPUP_REQUIRED" in blocker_codes, (
        f"V7-069 — expected GAS_TOPUP_REQUIRED for Sonic with empty S; got "
        f"{blocker_codes}"
    )
    gas_blocker = next(b for b in blockers if b["code"] == "GAS_TOPUP_REQUIRED")
    # The blocker title/detail must name the 'S' native token so the
    # frontend recovery card can route to a Sonic on-ramp.
    haystack = (gas_blocker.get("title", "") + " " +
                gas_blocker.get("detail", "") + " " +
                gas_blocker.get("cta", ""))
    assert " S " in haystack or haystack.endswith(" S") or " S." in haystack, (
        f"V7-069 — blocker should mention native symbol 'S'; got: {haystack}"
    )
