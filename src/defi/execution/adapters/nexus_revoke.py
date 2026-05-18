"""V7-074 — One-click revoke session-key adapter.

Emits a single `revoke_session_key` ExecutionStepV3 carrying the
deterministic `Nexus.uninstallModule(uint256,address,bytes)` calldata.
The state-machine verifier then mirror-checks the result on chain via
`src.auth.session_key_mirror.assert_session_key_revoked` (V7-073) and,
only on a confirmed mirror match, flips the unified state-store
(V7-075) entry to status=`revoked`.

Why a dedicated adapter (vs reusing `withdraw` or `approve`):

  * The action is its own primitive in StepAction — adapters route on
    the action string and the frontend "Revoke" CTA needs a typed
    signal to render the one-click button (not "Withdraw 0").
  * The calldata builder lives in `src/auth/biconomy_nexus.py`
    (`build_uninstall_session_key_module_calldata`) and we re-use it
    here so the selector (`0xa71763a8`) and ABI shape stay in lockstep.
  * The verifier is the mirror check, not a topic0 receipt scan — the
    mirror call works on any chain Nexus is deployed to without us
    having to maintain a per-chain `ModuleUninstalled` topic table.

The adapter intentionally has narrow scope: it does NOT quote (revokes
are free), does NOT take an asset_in (no token transfer), and does NOT
need an aggregator. The `build()` method assembles a one-step plan;
`supports()` declares the single (chain-agnostic, protocol="nexus",
action="revoke_session_key") capability triple.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from src.auth.biconomy_nexus import (
    NEXUS_MODULE_TYPE_VALIDATOR,
    build_uninstall_session_key_module_calldata,
)
from src.defi.execution.adapters.base import (
    CapabilityResult,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
    VerifyResult,
)
from src.defi.execution.models import (
    ExecutionStepV3,
    REVOKE_SESSION_KEY,
    UnsignedStepTransaction,
)


# Selector kept exposed so tests can pin the canonical 4-byte prefix
# without re-importing the private auth module symbol.
NEXUS_UNINSTALL_MODULE_SELECTOR = "0xa71763a8"


class NexusRevokeAdapter:
    """Adapter for the V7-074 one-click revoke step.

    Routing key: (chain=<any EVM>, protocol="nexus", action="revoke_session_key").
    """

    adapter_id = "nexus_revoke_v1"
    # Chain-agnostic: Nexus is deployed identically on every EIP-7702
    # chain we support. The set is left empty-sentinel here and the
    # `supports()` method does the actual EVM-vs-Solana gate so we
    # don't have to enumerate every chain id ever supported.
    chains: set[str] = set()
    protocols: set[str] = {"nexus", "biconomy_nexus"}
    actions: set[str] = {REVOKE_SESSION_KEY}

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        """Accept revoke_session_key for the Nexus protocol on any EVM chain.

        We refuse Solana explicitly (different account model — no Nexus).
        """
        if action != REVOKE_SESSION_KEY:
            return CapabilityResult(
                supported=False,
                reason=f"nexus_revoke only handles revoke_session_key (got {action!r})",
            )
        if (protocol or "").lower() not in {"nexus", "biconomy_nexus"}:
            return CapabilityResult(
                supported=False,
                reason=f"nexus_revoke only supports protocol=nexus (got {protocol!r})",
            )
        if (chain or "").lower() in {"solana", "sol"}:
            return CapabilityResult(
                supported=False,
                reason="Nexus is EVM-only; Solana session keys use a different module",
            )
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        """Revoke is gas-only — return a zero-fee quote shell.

        Callers that need a gas estimate must compute it at simulation
        time; the quote layer's "expected_amount_out" is meaningless
        for revoke (nothing is being swapped/staked/withdrawn).
        """
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=None,
            fees={"protocol_fee": "0", "note": "revoke is gas-only"},
            metadata={
                "action": REVOKE_SESSION_KEY,
                "selector": NEXUS_UNINSTALL_MODULE_SELECTOR,
            },
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        """Assemble the one-step revoke plan.

        Required `extra` keys:
          * `nexus_address` — the user's Nexus smart account (the `to`).
          * `module_address` — the session-key validator module to uninstall.

        We reuse `build_uninstall_session_key_module_calldata` from the
        auth module so the calldata layout exactly mirrors what the
        installer wrote on-chain — guaranteeing the mirror-check after
        broadcast lines up with the same module address.
        """
        extra = request.extra or {}
        nexus_address = extra.get("nexus_address") or extra.get("nexus_addr")
        module_address = extra.get("module_address") or extra.get("validator_module_address")
        if not nexus_address or not module_address:
            raise ValueError(
                "nexus_revoke build() requires extra.nexus_address + "
                "extra.module_address (the validator module to uninstall)."
            )
        calldata = build_uninstall_session_key_module_calldata(
            validator_module_address=module_address,
        )
        # Sanity check: the calldata must begin with the canonical
        # 0xa71763a8 uninstallModule selector. This is the V7-074 pin
        # the test asserts against.
        if not calldata.lower().startswith(NEXUS_UNINSTALL_MODULE_SELECTOR):
            raise AssertionError(
                f"nexus_revoke: built calldata missing selector "
                f"{NEXUS_UNINSTALL_MODULE_SELECTOR}: {calldata[:16]}…"
            )
        chain_id = extra.get("chain_id")
        step = ExecutionStepV3(
            step_id=f"step_{uuid4().hex[:12]}",
            index=0,
            action=REVOKE_SESSION_KEY,  # type: ignore[arg-type]
            title="Revoke session key",
            description=(
                "Uninstalls the validator module from your Nexus account. "
                "After this lands the agent can no longer sign on your behalf."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol="nexus",
            asset_in=None,
            asset_out=None,
            amount_in=None,
            amount_out=None,
            slippage_bps=0,
            duration_estimate_s=20,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=int(chain_id) if chain_id is not None else None,
                to=nexus_address,
                data="0x" + calldata if not calldata.startswith("0x") else calldata,
                value="0",
            ),
        )
        # Stamp the canonical module type into the recovery_hook so the
        # mirror-checker downstream knows which moduleType to query.
        step.recovery_hook = {
            "kind": "nexus_revoke_mirror",
            "module_type": NEXUS_MODULE_TYPE_VALIDATOR,
            "nexus_address": nexus_address,
            "module_address": module_address,
        }
        return [step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        """Verification is delegated to the on-chain mirror check.

        Callers should invoke `assert_session_key_revoked` from
        `src.auth.session_key_mirror` after the broadcast lands. We
        keep this stub here so the adapter satisfies the YieldAdapter
        Protocol surface without forcing the verifier to round-trip
        through receipt-log scanning (which would require a per-chain
        topic0 table for the `ModuleUninstalled` event).
        """
        return VerifyResult(
            confirmed=False,
            detail=(
                "nexus_revoke uses mirror-check verification — call "
                "src.auth.session_key_mirror.assert_session_key_revoked "
                "with the recovery_hook (nexus_address, module_address, "
                "module_type) instead of receipt-log scanning."
            ),
        )
