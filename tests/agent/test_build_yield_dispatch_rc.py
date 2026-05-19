"""Pin tests for build_yield_execution_plan RC fixes (RC3 / RC6 / RC8).

These tests pin the three financial-loss guards added to the planner:

- RC3: AMOUNT_NOT_CONFIRMED — refuse to build when the caller passes the
  legacy $1000/$100 placeholder default without confirming the amount.
  Earlier passes silently substituted $1000 when the prose carried no
  numeric amount; the user clicked Sign and stamped a 1000-unit supply.

- RC6: VERB_NOT_SUPPORTED — verb-aware dispatch table refuses to silently
  downgrade `borrow` / `repay` / etc. to `supply` when the protocol can
  only stake or only lend. Earlier passes fell through to the adapter
  registry and the first matching adapter would emit a supply step.

- RC8: CHAIN_KIND_MISMATCH — Solana-native assets (MSOL/JITOSOL/JLP/INF…)
  must force chain_kind=solana. Refuse builds where the chain stamp is
  EVM but the asset symbol is an SPL mint, otherwise the adapter either
  Enso-422s or — worse — signs a swap on a same-symbol scam token on the
  wrong chain.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.agent.tools.build_yield_execution_plan import build_yield_execution_plan


def _ctx(wallet: str = "0x1111111111111111111111111111111111111111") -> SimpleNamespace:
    return SimpleNamespace(wallet=wallet, evm_wallet=wallet, solana_wallet=None,
                            session_id=None)


def _sol_ctx() -> SimpleNamespace:
    sol = "So11111111111111111111111111111111111111112"
    return SimpleNamespace(wallet=sol, solana_wallet=sol, evm_wallet=None,
                            session_id=None)


def _is_ok(envelope) -> bool:
    """Accept both pydantic ToolEnvelope and plain-dict shapes."""
    if hasattr(envelope, "ok"):
        return bool(envelope.ok)
    if isinstance(envelope, dict):
        return bool(envelope.get("ok"))
    return False


def _data_of(envelope) -> dict:
    if hasattr(envelope, "data"):
        return envelope.data or {}
    if isinstance(envelope, dict):
        return envelope.get("data") or {}
    return {}


def _plan_from(envelope) -> dict:
    """Pull the execution_plan_v3 payload out of the ok_envelope return."""
    assert _is_ok(envelope), f"build returned err envelope: {envelope}"
    data = _data_of(envelope)
    plan = data.get("plan") if isinstance(data, dict) else None
    return plan or {}


def _blocker_codes(plan: dict) -> list[str]:
    return [b.get("code") for b in (plan.get("blockers") or [])]


# ---------------------------------------------------------------------------
# RC8 — CHAIN_KIND_MISMATCH for Solana-native assets on EVM chains
# ---------------------------------------------------------------------------

class TestRC8ChainKindMismatch:
    """Solana-native SPL mints (MSOL, JITOSOL, JLP, INF, ...) must NEVER
    route to an EVM adapter. The build path refuses + emits
    CHAIN_KIND_MISMATCH so the runtime can re-prompt the user."""

    @pytest.mark.asyncio
    async def test_jitosol_on_ethereum_refused(self):
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="lido", action="stake",
            asset_in="JITOSOL", amount_in=1.0,
            extra={"amount_confirmed": True},
        )
        plan = _plan_from(env)
        assert "CHAIN_KIND_MISMATCH" in _blocker_codes(plan), (
            f"JITOSOL on ethereum should emit CHAIN_KIND_MISMATCH; got "
            f"{_blocker_codes(plan)}"
        )

    @pytest.mark.asyncio
    async def test_msol_on_arbitrum_refused(self):
        env = await build_yield_execution_plan(
            _ctx(),
            chain="arbitrum", protocol="aave-v3", action="supply",
            asset_in="MSOL", amount_in=10.0,
            extra={"amount_confirmed": True},
        )
        plan = _plan_from(env)
        assert "CHAIN_KIND_MISMATCH" in _blocker_codes(plan)

    @pytest.mark.asyncio
    async def test_jlp_on_base_refused(self):
        env = await build_yield_execution_plan(
            _ctx(),
            chain="base", protocol="aave-v3", action="supply",
            asset_in="JLP", amount_in=5.0,
            extra={"amount_confirmed": True},
        )
        plan = _plan_from(env)
        assert "CHAIN_KIND_MISMATCH" in _blocker_codes(plan)

    @pytest.mark.asyncio
    async def test_inf_on_polygon_refused(self):
        env = await build_yield_execution_plan(
            _ctx(),
            chain="polygon", protocol="aave-v3", action="supply",
            asset_in="INF", amount_in=2.0,
            extra={"amount_confirmed": True},
        )
        plan = _plan_from(env)
        assert "CHAIN_KIND_MISMATCH" in _blocker_codes(plan)

    @pytest.mark.asyncio
    async def test_msol_on_solana_passes_chain_kind_gate(self):
        """Happy path: MSOL on solana must NOT trip CHAIN_KIND_MISMATCH.
        The plan may still hit downstream blockers (registry / preflight)
        — we only assert this specific gate did not fire."""
        env = await build_yield_execution_plan(
            _sol_ctx(),
            chain="solana", protocol="marinade", action="stake",
            asset_in="MSOL", amount_in=1.0,
            extra={"amount_confirmed": True},
        )
        # Either ok_envelope (real plan) or err_envelope (downstream issue).
        # The chain_kind gate must NOT have fired.
        if _is_ok(env):
            plan = _plan_from(env)
            assert "CHAIN_KIND_MISMATCH" not in _blocker_codes(plan)


# ---------------------------------------------------------------------------
# RC6 — VERB_NOT_SUPPORTED dispatch refuses silent supply-downgrade
# ---------------------------------------------------------------------------

class TestRC6VerbDispatch:
    """Verbs not in the protocol's supported set must emit
    VERB_NOT_SUPPORTED — never silently fall through to supply."""

    @pytest.mark.asyncio
    async def test_borrow_on_lido_refused(self):
        """Lido is stake-only. `borrow` must NOT silently become `supply`."""
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="lido", action="borrow",
            asset_in="ETH", amount_in=1.0,
            extra={"amount_confirmed": True},
        )
        plan = _plan_from(env)
        assert "VERB_NOT_SUPPORTED" in _blocker_codes(plan), (
            f"Lido + borrow should emit VERB_NOT_SUPPORTED; got "
            f"{_blocker_codes(plan)}"
        )

    @pytest.mark.asyncio
    async def test_repay_on_rocket_pool_refused(self):
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="rocket-pool", action="repay",
            asset_in="ETH", amount_in=1.0,
            extra={"amount_confirmed": True},
        )
        plan = _plan_from(env)
        assert "VERB_NOT_SUPPORTED" in _blocker_codes(plan)

    @pytest.mark.asyncio
    async def test_borrow_on_yearn_refused(self):
        """Yearn vaults are deposit/withdraw only."""
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="yearn", action="borrow",
            asset_in="USDC", amount_in=100.0,
            extra={"amount_confirmed": True},
        )
        plan = _plan_from(env)
        assert "VERB_NOT_SUPPORTED" in _blocker_codes(plan)

    @pytest.mark.asyncio
    async def test_borrow_on_aave_v3_passes_dispatch(self):
        """Happy path: Aave V3 explicitly supports borrow; dispatch must
        NOT block. (Downstream may still hit blockers, but VERB gate fires
        cleanly.)"""
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="aave-v3", action="borrow",
            asset_in="USDC", amount_in=50.0,
            extra={"amount_confirmed": True},
        )
        if _is_ok(env):
            plan = _plan_from(env)
            assert "VERB_NOT_SUPPORTED" not in _blocker_codes(plan)

    @pytest.mark.asyncio
    async def test_unknown_protocol_skips_dispatch(self):
        """Protocols not in the dispatch table are NOT blocked here —
        they fall through to the registry which has its own coverage check.
        This pin keeps the dispatch table from over-blocking."""
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="some-unknown-protocol", action="supply",
            asset_in="USDC", amount_in=100.0,
            extra={"amount_confirmed": True},
        )
        # Either ok or err — we only check the VERB gate didn't fire.
        if _is_ok(env):
            plan = _plan_from(env)
            assert "VERB_NOT_SUPPORTED" not in _blocker_codes(plan)


# ---------------------------------------------------------------------------
# RC3 — AMOUNT_NOT_CONFIRMED refuses placeholder $1000 / $100
# ---------------------------------------------------------------------------

class TestRC3AmountConfirmation:
    """Placeholder amounts (1000 / 100) without an explicit
    amount_confirmed=True flag must emit AMOUNT_NOT_CONFIRMED."""

    @pytest.mark.asyncio
    async def test_1000_placeholder_refused(self):
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="aave-v3", action="supply",
            asset_in="USDC", amount_in=1000.0,
            # Note: NO amount_confirmed flag
            extra={},
        )
        plan = _plan_from(env)
        assert "AMOUNT_NOT_CONFIRMED" in _blocker_codes(plan), (
            f"$1000 placeholder must emit AMOUNT_NOT_CONFIRMED; got "
            f"{_blocker_codes(plan)}"
        )

    @pytest.mark.asyncio
    async def test_100_real_user_amount_not_blocked(self):
        # $100 is a real user-typed amount, NOT a legacy placeholder.
        # Only $1000 (the historical default) triggers the placeholder
        # heuristic — $100 must reach normal build path.
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="aave-v3", action="supply",
            asset_in="USDC", amount_in=100.0,
            extra={},
        )
        plan = _plan_from(env)
        assert "AMOUNT_NOT_CONFIRMED" not in _blocker_codes(plan)

    @pytest.mark.asyncio
    async def test_1000_with_confirmation_passes(self):
        """Explicit confirmation lets $1000 through (real user-typed amount)."""
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="aave-v3", action="supply",
            asset_in="USDC", amount_in=1000.0,
            extra={"amount_confirmed": True},
        )
        # AMOUNT gate must not fire. Downstream may still block.
        if _is_ok(env):
            plan = _plan_from(env)
            assert "AMOUNT_NOT_CONFIRMED" not in _blocker_codes(plan)

    @pytest.mark.asyncio
    async def test_non_placeholder_amount_passes(self):
        """An odd amount like 37.5 USDC is clearly user-typed; allow."""
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="aave-v3", action="supply",
            asset_in="USDC", amount_in=37.5,
            extra={},
        )
        if _is_ok(env):
            plan = _plan_from(env)
            assert "AMOUNT_NOT_CONFIRMED" not in _blocker_codes(plan)

    @pytest.mark.asyncio
    async def test_lifecycle_withdraw_zero_passes(self):
        """`withdraw` + amount=0 is the canonical 'max' sentinel — must
        not trip the placeholder gate."""
        env = await build_yield_execution_plan(
            _ctx(),
            chain="ethereum", protocol="aave-v3", action="withdraw",
            asset_in="USDC", amount_in=0,
            extra={},
        )
        if _is_ok(env):
            plan = _plan_from(env)
            assert "AMOUNT_NOT_CONFIRMED" not in _blocker_codes(plan)
