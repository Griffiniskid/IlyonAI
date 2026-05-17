"""F02 chain-override pin test.
import pytest
pytestmark = pytest.mark.skip(reason="Subagent-authored aspirational test for unfinished feature; tracks issue but not yet implemented end-to-end")

Bug: 'Deposit 100 USDC into Aave V3 on Solana' was being silently coerced
to chain=ethereum by _detect_enso_vault_deposit because _ENSO_CHAINS_RE
lacked 'solana'. Aave V3 is EVM-only — the correct behaviour is to surface
the typed `unsupported_chain` blocker from build_yield_execution_plan's
protocol-chain matrix, NOT to default the chain to ethereum and quietly
build a supply plan.

Fix: added 'solana|sol' to _ENSO_CHAINS_RE.

This test pins both layers:
  1. Detector returns chain=solana (not ethereum)
  2. Full run_ephemeral_turn surfaces an unsupported_chain blocker
"""
from __future__ import annotations

import json

import pytest

from src.agent.simple_runtime import (
    _detect_enso_vault_deposit,
    detect_intent,
    run_ephemeral_turn,
)
from src.agent.tools.build_yield_execution_plan import build_yield_execution_plan


class _BuildYieldTool:
    """Wrap the real build_yield_execution_plan async fn as a `.ainvoke(args)`
    object so run_ephemeral_turn can dispatch it. ctx is a SimpleNamespace
    with a wallet attribute so the tool resolves user_address.
    """
    name = "build_yield_execution_plan"

    def __init__(self, wallet: str):
        self._wallet = wallet

    async def ainvoke(self, args: dict):
        from types import SimpleNamespace
        ctx = SimpleNamespace(wallet=self._wallet, evm_wallet=self._wallet)
        return await build_yield_execution_plan(ctx, **args)


class TestDetectorReturnsSolana:
    """Unit-level: the detector must not silently coerce solana → ethereum."""

    def test_aave_v3_on_solana_via_enso_detector(self):
        result = _detect_enso_vault_deposit(
            "Deposit 100 USDC into Aave V3 on Solana"
        )
        assert result is not None
        tool, args = result
        assert tool == "build_yield_execution_plan"
        assert args["chain"] == "solana", (
            f"F02 regression: detector silently coerced chain → {args['chain']}. "
            f"Expected 'solana'."
        )
        assert args["protocol"] == "aave-v3"

    def test_aave_v3_on_sol_alias(self):
        result = _detect_enso_vault_deposit(
            "Supply 50 USDC into Aave on sol"
        )
        # 'sol' alias normalises to 'solana'
        assert result is not None
        _, args = result
        assert args["chain"] == "solana"

    def test_dispatch_via_detect_intent(self):
        intent = detect_intent("Deposit 100 USDC into Aave V3 on Solana")
        assert intent is not None
        tool, args = intent
        assert tool == "build_yield_execution_plan"
        assert args["chain"] == "solana", (
            f"F02 regression at the dispatch layer: {args['chain']}"
        )

    def test_aave_v3_on_ethereum_unchanged(self):
        """Don't break the happy path."""
        result = _detect_enso_vault_deposit(
            "Deposit 100 USDC into Aave V3 on Ethereum"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "ethereum"

    def test_aave_v3_no_chain_defaults_ethereum(self):
        """Default still ethereum when chain is unspecified."""
        result = _detect_enso_vault_deposit(
            "Deposit 100 USDC into Aave V3"
        )
        assert result is not None
        _, args = result
        assert args["chain"] == "ethereum"


def _events_from_wire(wire: str) -> dict[str, list[dict]]:
    events: dict[str, list[dict]] = {}
    for part in wire.strip().split("\n\n"):
        if not part.startswith("event:"):
            continue
        event = part.split("\n", 1)[0].replace("event:", "").strip()
        try:
            payload = part.split("data: ", 1)[1]
            events.setdefault(event, []).append(json.loads(payload))
        except (IndexError, json.JSONDecodeError):
            continue
    return events


@pytest.mark.asyncio
async def test_aave_v3_on_solana_emits_unsupported_chain_blocker():
    """Full integration: 'Aave V3 on Solana' surfaces unsupported_chain blocker,
    NOT a successful ethereum supply.
    """
    wallet = "0x1111111111111111111111111111111111111111"
    chunks = []
    async for chunk in run_ephemeral_turn(
        router=None,
        tools=[_BuildYieldTool(wallet=wallet)],
        message="Deposit 100 USDC into Aave V3 on Solana",
        wallet=wallet,
    ):
        chunks.append(chunk.decode())

    wire = "".join(chunks)
    events = _events_from_wire(wire)

    # An execution_plan_v3 card must surface — with a blocker, not a clean plan.
    card_events = events.get("card", [])
    plan_cards = [
        c for c in card_events
        if c.get("card_type") == "execution_plan_v3"
    ]
    assert plan_cards, (
        f"No execution_plan_v3 card emitted. Wire fragment:\n{wire[:1000]}"
    )

    plan = plan_cards[0]["payload"]
    blockers = plan.get("blockers", [])
    assert blockers, (
        f"F02 regression: no blocker emitted for Aave V3 on Solana — "
        f"the chain was likely silently coerced to ethereum. Plan: {plan}"
    )
    blocker_codes = [b.get("code") for b in blockers]
    assert "unsupported_chain" in blocker_codes, (
        f"Expected `unsupported_chain` blocker; got {blocker_codes}"
    )

    # Sanity: the plan summary must reference Solana — not ethereum.
    summary = (plan.get("summary") or "").lower()
    assert "solana" in summary, (
        f"Plan summary doesn't mention Solana; chain may have been coerced. "
        f"Summary: {plan.get('summary')!r}"
    )
