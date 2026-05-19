"""RC16 pin tests — per-tool HTTP timeout in the tool dispatcher.

Pass A surfaced 17.5% of G-category turns (and multiple F/H/I/enso turns)
hanging in `build_yield_execution_plan` with a 90s curl client timeout. The
root cause was no top-level timeout around tool dispatch: an upstream RPC /
Enso / DefiLlama hang wedged the SSE stream until the client cap fired and
the agent emitted a fabricated card from partial state — a financial-loss
vector.

These pins assert:
  1. Every tool registered via `register_all_tools` has a SLO budget in
     `_TOOL_SLO_SECONDS` (or falls back to a safe default).
  2. A stubbed tool that sleeps longer than its SLO is killed by the
     dispatcher within SLO + 1s and emits a TOOL_TIMEOUT err_envelope.
  3. The TOOL_TIMEOUT envelope carries `ok=False` so downstream code
     can never accidentally fabricate a card from None data.
  4. The default SLO bound is ≤ the 90s SSE client cap with margin.

Run with:
    pytest tests/agent/tools/test_tool_dispatch_timeout.py -q
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from src.agent.tools import (
    _TOOL_REGISTRY,
    _TOOL_SLO_DEFAULT,
    _TOOL_SLO_SECONDS,
    _slo_for,
    register_all_tools,
)
from src.api.schemas.agent import ToolEnvelope


def test_every_registered_tool_has_a_slo_budget_or_default():
    """Every tool name in the registry must resolve to a finite, sane SLO."""
    for name in _TOOL_REGISTRY:
        slo = _slo_for(name)
        assert 1.0 <= slo <= 90.0, (
            f"tool {name!r} SLO {slo} outside [1, 90]s — must fit within "
            f"the 90s SSE client cap with margin."
        )


def test_default_slo_within_client_cap():
    """Safety ceiling must leave headroom under the 90s client cap."""
    assert _TOOL_SLO_DEFAULT <= 75.0


def test_search_defi_opportunities_slo_30s_per_rc16_spec():
    """RC16 explicit default: search_defi_opportunities = 30s."""
    assert _TOOL_SLO_SECONDS["search_defi_opportunities"] == 30.0


def test_build_yield_execution_plan_slo_45s_per_rc16_spec():
    """RC16 explicit default: build_yield_execution_plan = 45s.

    Pass A found this exact tool hanging on G02/t1/t4, G04/t1, G05/t1/t2,
    G09/t1/t4. The SLO sized to actual upstream latency budget."""
    assert _TOOL_SLO_SECONDS["build_yield_execution_plan"] == 45.0


def test_compose_plan_slo_60s_per_rc16_spec():
    """RC16 explicit default: compose_plan = 60s."""
    assert _TOOL_SLO_SECONDS["compose_plan"] == 60.0


def test_build_swap_tx_slo_45s_per_rc16_spec():
    """RC16 explicit default: enso shortcut route = 45s."""
    assert _TOOL_SLO_SECONDS["build_swap_tx"] == 45.0


def test_build_bridge_tx_slo_30s_per_rc16_spec():
    """RC16 explicit default: deBridge order = 30s."""
    assert _TOOL_SLO_SECONDS["build_bridge_tx"] == 30.0


@pytest.mark.asyncio
async def test_dispatcher_kills_hung_tool_within_slo_window(monkeypatch):
    """A tool that sleeps longer than its SLO is killed by the dispatcher
    and emits a TOOL_TIMEOUT err_envelope within SLO + 1s wall time.

    This is the critical RC16 financial-loss guard: no fabricated card
    from partial state — the envelope must be ok=False with code
    TOOL_TIMEOUT."""
    # Stub the get_token_price tool so it sleeps past its 15s SLO. We
    # override the SLO to 0.5s so the test runs fast but still exercises
    # the wait_for path.
    monkeypatch.setitem(_TOOL_SLO_SECONDS, "get_token_price", 0.5)

    async def _slow_get_token_price(ctx, **_kw):  # noqa: ARG001
        await asyncio.sleep(5.0)  # 10x the SLO — must be killed
        return {"price": 1.0}

    monkeypatch.setattr(
        "src.agent.tools.get_token_price", _slow_get_token_price
    )
    # The registry caches the function reference at import time. Patch
    # both the module-level alias and the registry tuple so register_all_tools
    # picks up our slow stub.
    monkeypatch.setitem(
        _TOOL_REGISTRY,
        "get_token_price",
        (_slow_get_token_price, "stub"),
    )

    services = MagicMock()
    tools = register_all_tools(services, user_id=1, wallet="0xdEAD")
    price_tool = next(t for t in tools if t.name == "get_token_price")

    t0 = time.monotonic()
    result = await price_tool.coroutine(symbol="ETH")
    elapsed = time.monotonic() - t0

    # The dispatcher must have killed the call well within SLO+1s.
    assert elapsed < 1.5, (
        f"TOOL_TIMEOUT did not fire in time: {elapsed:.2f}s elapsed for a "
        f"0.5s SLO (expected < 1.5s)"
    )
    assert isinstance(result, ToolEnvelope)
    assert result.ok is False, "TOOL_TIMEOUT envelope must be ok=False"
    assert result.error is not None
    assert result.error.code == "TOOL_TIMEOUT", (
        f"expected code=TOOL_TIMEOUT, got {result.error.code!r}"
    )
    assert "get_token_price" in (result.error.message or "")
    # Hard rule: never fabricate a card from None data.
    assert result.card_payload is None


@pytest.mark.asyncio
async def test_dispatcher_passes_through_normal_tool_results(monkeypatch):
    """Non-hung tools must complete normally — the wait_for wrapper must
    not change the happy-path behaviour."""
    from src.agent.tools._base import ok_envelope

    async def _fast(ctx, **_kw):  # noqa: ARG001
        return ok_envelope(data={"ok": True})

    monkeypatch.setitem(_TOOL_REGISTRY, "get_token_price", (_fast, "stub"))
    monkeypatch.setattr("src.agent.tools.get_token_price", _fast)

    services = MagicMock()
    tools = register_all_tools(services, user_id=1, wallet="0xdEAD")
    price_tool = next(t for t in tools if t.name == "get_token_price")

    result = await price_tool.coroutine(symbol="ETH")
    assert isinstance(result, ToolEnvelope)
    assert result.ok is True
    assert result.data == {"ok": True}
