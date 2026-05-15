"""Pendle V2 three-mode adapter scaffolding — spec §8 Pendle deep.

Pendle V2 has three deposit modes per spec:
  1. mintPyFromToken   — mint PT + YT from any token
  2. swapTokenForPt    — buy PT directly (gives only price exposure)
  3. addLiquidityFromToken — add LP (earns swap fees + voting)

This module ships the address registry + selector constants + action
membership so the registry picks Pendle for matching intents. Full
calldata encoding follows in a focused commit once the IDL surface
stabilises across Pendle V4 SDK upgrades (3 selector overloads each).
"""
from __future__ import annotations

from dataclasses import dataclass

from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.models import ExecutionStepV3


# Pendle V2 Router (latest stable per docs) per chain.
_PENDLE_ROUTER: dict[str, str] = {
    "ethereum": "0x888888888889758F76e7103c6CbF23ABbF58F946",
    "arbitrum": "0x888888888889758F76e7103c6CbF23ABbF58F946",
    "optimism": "0x888888888889758F76e7103c6CbF23ABbF58F946",
    "bsc":      "0x888888888889758F76e7103c6CbF23ABbF58F946",
    "base":     "0x888888888889758F76e7103c6CbF23ABbF58F946",
    "mantle":   "0x888888888889758F76e7103c6CbF23ABbF58F946",
}

# Selectors per PendleRouterV4 dispatcher.
# Pendle's router uses overloaded calls — the canonical IDs:
SEL_MINT_PY_FROM_TOKEN = "0xc81f847a"
SEL_SWAP_TOKEN_FOR_PT = "0x594a88cc"
SEL_ADD_LIQUIDITY_FROM_TOKEN = "0x9f9da99e"


@dataclass
class PendleV2Adapter:
    adapter_id: str = "pendle-v2"
    chains: frozenset[str] = frozenset(_PENDLE_ROUTER.keys())
    protocols: frozenset[str] = frozenset({"pendle", "pendle-v2"})
    actions: frozenset[str] = frozenset({
        "mint_py", "swap_for_pt", "add_liquidity",
        "deposit_lp", "provide_liquidity",
    })

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if chain not in self.chains:
            return CapabilityResult(False, None, f"Pendle V2 not on {chain}.")
        if protocol not in self.protocols:
            return CapabilityResult(False, None, f"Adapter is for Pendle, not {protocol}.")
        if action not in self.actions:
            return CapabilityResult(False, None, f"Pendle adapter does not handle {action}.")
        return CapabilityResult(True, self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=None,
            fees={"protocol": "Pendle pool fee varies by market"},
            metadata={"protocol": "pendle-v2", "chain": request.chain},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        """Per-mode dispatch — each Pendle mode emits its own typed step.

        Pendle V4 router calldata uses nested structs (ApproxParams,
        TokenInput, LimitOrderData) whose `guessOffchain` differs by market.
        Hand-rolled values risk slippage reverts → we route the calldata
        composition through the frontend Pendle SDK and keep the plan
        authoritative on intent + selector + market + receiver only.
        """
        from src.defi.execution.models import make_step
        import time

        chain_id_map = {
            "ethereum": 1, "arbitrum": 42161, "optimism": 10,
            "bsc": 56, "base": 8453, "mantle": 5000,
        }
        chain_id = chain_id_map.get(request.chain, 1)
        router = _PENDLE_ROUTER.get(request.chain)
        if router is None:
            raise ValueError(f"Pendle V2 router not registered on {request.chain}.")

        extra = request.extra or {}
        # Epoch-boundary blocker — Pendle markets expire; the caller should
        # surface PENDING_EPOCH_ENTRY when the chosen market is past expiry.
        market_expiry_ts = extra.get("market_expiry_ts")
        if market_expiry_ts is not None:
            try:
                expiry = int(market_expiry_ts)
            except (TypeError, ValueError):
                expiry = 0
            if expiry > 0 and expiry < int(time.time()):
                return [
                    make_step(
                        index=1, action="deposit_lp",
                        title=f"Pendle market expired at ts={expiry}",
                        description=(
                            "The selected Pendle V2 market has passed its expiry "
                            "timestamp. Choose an active market or wait for the "
                            "next epoch to roll over."
                        ),
                        chain=request.chain, wallet="MetaMask", protocol="pendle-v2",
                        asset_in=request.asset_in, amount_in=str(request.amount_in),
                        slippage_bps=request.slippage_bps,
                        blocker_codes=["PENDING_EPOCH_ENTRY"],
                    ),
                ]

        action = (extra.get("action") or "add_liquidity").lower()
        market = extra.get("market") or extra.get("market_address")
        if not market:
            raise ValueError(
                "Pendle V2 build needs extra.market (the PT/YT/LP market address)."
            )

        if action in {"mint_py", "mint_py_from_token"}:
            selector_pin = SEL_MINT_PY_FROM_TOKEN
            mode_label = "mintPyFromToken"
        elif action in {"swap_for_pt", "swap_token_for_pt"}:
            selector_pin = SEL_SWAP_TOKEN_FOR_PT
            mode_label = "swapTokenForPt"
        else:
            selector_pin = SEL_ADD_LIQUIDITY_FROM_TOKEN
            mode_label = "addLiquidityFromToken"

        return [
            make_step(
                index=1,
                action=action if action in {"mint_py", "swap_for_pt"} else "add_liquidity",
                title=f"Pendle V2 {mode_label} on market {market[:10]}…",
                description=(
                    f"Pendle V2 Router {router} call to {mode_label} (selector "
                    f"{selector_pin}). Frontend Pendle SDK fills ApproxParams "
                    f"+ TokenInput from the live market state before signing. "
                    f"Market: {market}. Input: {request.amount_in} {request.asset_in}."
                ),
                chain=request.chain, wallet="MetaMask", protocol="pendle-v2",
                asset_in=request.asset_in, amount_in=str(request.amount_in),
                slippage_bps=request.slippage_bps,
                blocker_codes=["NEEDS_FRONTEND_SDK"],
            ),
        ]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(
            confirmed=False,
            detail="Pendle V2 receipt verify: read SY/PT/YT balanceOf delta or LP shares.",
        )
