"""V7-074 — Pin test for the one-click revoke session-key adapter.

Verifies that `src/defi/execution/adapters/nexus_revoke.py`:

  1. Declares `revoke_session_key` in its supported actions and
     `StepAction` exposes the `REVOKE_SESSION_KEY` constant.
  2. `supports()` accepts the (evm_chain, "nexus", "revoke_session_key")
     triple and refuses Solana / non-Nexus protocols.
  3. `build()` returns a single ExecutionStepV3 whose
     transaction.data starts with the canonical `0xa71763a8`
     uninstallModule selector.
  4. The recovery_hook embeds the module-type + nexus_address +
     module_address so the mirror-checker (V7-073) can re-query
     the on-chain state by intent_id.
  5. `build()` raises when `extra` is missing the required addresses.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.adapters.nexus_revoke import (
    NEXUS_UNINSTALL_MODULE_SELECTOR,
    NexusRevokeAdapter,
)
from src.defi.execution.models import REVOKE_SESSION_KEY


_USER = "0x" + "11" * 20
_NEXUS = "0x" + "ab" * 20
_MODULE = "0x" + "cd" * 20


def _make_build_request(**extra_overrides) -> YieldBuildRequest:
    extra = {
        "nexus_address": _NEXUS,
        "module_address": _MODULE,
        "chain_id": 8453,
        **extra_overrides,
    }
    return YieldBuildRequest(
        chain="base",
        protocol="nexus",
        asset_in="ETH",
        amount_in=Decimal("0"),
        user_address=_USER,
        extra=extra,
    )


def test_adapter_advertises_revoke_session_key_action():
    """The adapter exposes revoke_session_key in its actions set."""
    a = NexusRevokeAdapter()
    assert REVOKE_SESSION_KEY in a.actions
    assert REVOKE_SESSION_KEY == "revoke_session_key"


def test_step_action_constant_is_exported_from_models():
    """`REVOKE_SESSION_KEY` is importable from models for downstream
    routing layers (state-machine, frontend bridge, etc.)."""
    from src.defi.execution import models as m

    assert hasattr(m, "REVOKE_SESSION_KEY")
    assert m.REVOKE_SESSION_KEY == "revoke_session_key"


def test_supports_accepts_revoke_on_evm_nexus():
    """supports() returns truthy for the canonical triple."""
    a = NexusRevokeAdapter()
    cap = a.supports(chain="base", protocol="nexus", action="revoke_session_key")
    assert cap.supported is True
    assert cap.adapter_id == "nexus_revoke_v1"


def test_supports_refuses_solana():
    """Nexus is EVM-only — Solana must be refused."""
    a = NexusRevokeAdapter()
    cap = a.supports(chain="solana", protocol="nexus", action="revoke_session_key")
    assert cap.supported is False
    assert "EVM-only" in (cap.reason or "")


def test_supports_refuses_non_nexus_protocol():
    """Other protocols (aave, curve, ...) are not Nexus."""
    a = NexusRevokeAdapter()
    cap = a.supports(chain="base", protocol="aave_v3", action="revoke_session_key")
    assert cap.supported is False


def test_supports_refuses_other_actions():
    """Adapter only handles revoke_session_key — not supply/withdraw/etc."""
    a = NexusRevokeAdapter()
    cap = a.supports(chain="base", protocol="nexus", action="supply")
    assert cap.supported is False


def test_build_returns_single_revoke_step_with_canonical_selector():
    """build() returns a 1-step plan; tx.data starts with 0xa71763a8."""
    a = NexusRevokeAdapter()
    steps = asyncio.run(a.build(_make_build_request()))
    assert len(steps) == 1
    step = steps[0]
    assert step.action == REVOKE_SESSION_KEY
    assert step.transaction is not None
    assert step.transaction.to == _NEXUS
    assert step.transaction.data is not None
    # Critical pin: the calldata MUST start with the uninstallModule selector.
    assert step.transaction.data.lower().startswith(
        NEXUS_UNINSTALL_MODULE_SELECTOR
    )


def test_build_step_carries_recovery_hook_for_mirror_check():
    """recovery_hook embeds the V7-073 mirror-check params."""
    a = NexusRevokeAdapter()
    steps = asyncio.run(a.build(_make_build_request()))
    rh = steps[0].recovery_hook
    assert rh is not None
    assert rh["kind"] == "nexus_revoke_mirror"
    assert rh["nexus_address"] == _NEXUS
    assert rh["module_address"] == _MODULE
    assert rh["module_type"] == 1  # NEXUS_MODULE_TYPE_VALIDATOR


def test_build_raises_when_addresses_missing():
    """Missing nexus_address or module_address → ValueError."""
    a = NexusRevokeAdapter()
    bad = _make_build_request()
    bad.extra = {"nexus_address": _NEXUS}  # missing module_address
    with pytest.raises(ValueError):
        asyncio.run(a.build(bad))


def test_quote_returns_zero_fee_shell():
    """Revoke is gas-only — quote returns metadata only."""
    from src.defi.execution.adapters.base import YieldQuoteRequest

    a = NexusRevokeAdapter()
    quote = asyncio.run(
        a.quote(
            YieldQuoteRequest(
                chain="base",
                protocol="nexus",
                asset_in="ETH",
                amount_in=Decimal("0"),
            )
        )
    )
    assert quote.adapter_id == "nexus_revoke_v1"
    assert quote.metadata["selector"] == NEXUS_UNINSTALL_MODULE_SELECTOR
    assert quote.metadata["action"] == REVOKE_SESSION_KEY
