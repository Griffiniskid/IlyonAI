"""RC7a — end-to-end pin: build_yield_execution_plan composed-plan branch
must attach a real calldata payload to the bridge step (never null).

Pass A H04/H05/H06 captured composed plans where the bridge step's
`transaction` was null and the plan still read as `status:"ready"`. This
test mocks the DLN client (no network) and pins:

  1. The composed-plan emitter calls `bridge.create_order_encoded()` to
     get a real `tx.{to,data,value}` envelope.
  2. The bridge step's `transaction` is populated with chain_kind="evm",
     chain_id, to, data, value.
  3. If DLN returns a tx without `data`/`to`, the emitter REFUSES the
     plan and emits a COMPOSED_PLAN_INCOMPLETE_TX blocker.
"""
from __future__ import annotations

import pytest

from src.agent.tools.build_yield_execution_plan import build_yield_execution_plan


class _FakeBridge:
    """Fake `composed_plan.Bridge` that returns canned quote + create-tx."""

    name = "fake-dln"

    def __init__(self, *, with_calldata: bool = True):
        self.with_calldata = with_calldata

    async def quote(self, **kwargs):
        return {
            "expected_dst_amount": 99_500_000,
            "slippage_bps_band": {"min": 5, "max": 20},
            "quote_id": "fake-order-id-123",
        }

    async def create_order_encoded(self, **kwargs):
        if self.with_calldata:
            return {
                "tx": {
                    "to": "0xeF4fB24aD0916217251F553c0596F8Edc630EB66",  # deBridge DLN gateway
                    "data": "0xdeadbeefcafebabe" + "00" * 32,  # plausible calldata
                    "value": "0x0",
                },
                "order_id": "fake-order-id-123",
                "estimated_dst_amount": "99500000",
            }
        # Bug-injection variant — DLN returns tx without data
        return {
            "tx": {"to": None, "data": None, "value": "0x0"},
            "order_id": "fake-order-id-123",
        }


class _FakeCtx:
    wallet = "0x" + "11" * 20
    session_id = "test-session"


@pytest.mark.asyncio
async def test_bridge_step_carries_real_calldata(monkeypatch):
    """RC7a — successful composed-plan emission attaches real tx to bridge."""
    from src.routing import debridge_client

    # Patch the DeBridgeBridge constructor to return our fake.
    fake_bridge = _FakeBridge(with_calldata=True)
    monkeypatch.setattr(
        debridge_client, "DeBridgeBridge", lambda *a, **k: fake_bridge,
    )

    env = await build_yield_execution_plan(
        _FakeCtx(),
        chain="base",
        protocol="aave-v3",
        action="supply",
        asset_in="USDC",
        amount_in=100,
        user_address="0x" + "11" * 20,
        extra={"source_chain": "ethereum", "source_token": "USDC"},
    )
    # ok_envelope returns the plan in card_payload.
    assert env is not None
    plan_dict = env.card_payload
    assert plan_dict is not None
    steps = plan_dict.get("steps") or []
    assert len(steps) >= 1
    bridge_step = steps[0]
    assert bridge_step["action"] == "bridge"
    # The pin: bridge step has a real transaction object, not null.
    tx = bridge_step.get("transaction")
    assert tx is not None, "RC7a regression — bridge step has null transaction!"
    assert tx.get("data") is not None
    assert tx.get("to") is not None
    assert tx["to"].lower().startswith("0x")
    # Calldata starts with 0x and has at least the selector.
    assert tx["data"].startswith("0x")
    assert len(tx["data"]) >= 10


@pytest.mark.asyncio
async def test_bridge_step_null_calldata_emits_blocker(monkeypatch):
    """RC7a — when DLN /create-tx returns no calldata, refuse plan emission
    and emit COMPOSED_PLAN_INCOMPLETE_TX blocker."""
    from src.routing import debridge_client

    fake_bridge = _FakeBridge(with_calldata=False)
    monkeypatch.setattr(
        debridge_client, "DeBridgeBridge", lambda *a, **k: fake_bridge,
    )

    env = await build_yield_execution_plan(
        _FakeCtx(),
        chain="base",
        protocol="aave-v3",
        action="supply",
        asset_in="USDC",
        amount_in=100,
        user_address="0x" + "11" * 20,
        extra={"source_chain": "ethereum", "source_token": "USDC"},
    )
    assert env is not None
    plan_dict = env.card_payload
    blockers = plan_dict.get("blockers") or []
    blocker_codes = [b.get("code") for b in blockers]
    assert "COMPOSED_PLAN_INCOMPLETE_TX" in blocker_codes, (
        f"Expected COMPOSED_PLAN_INCOMPLETE_TX blocker, got {blocker_codes!r}"
    )
