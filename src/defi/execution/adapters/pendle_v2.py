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
        # Calldata encoding for the 3 modes lands in a follow-up commit.
        # Returning a typed blocker keeps the registry hit but routes the
        # user back to the Pendle app via pool_link until the encoder
        # ships.
        from src.defi.execution.models import KNOWN_BLOCKER_CODES, make_step
        chain_id_map = {"ethereum": 1, "arbitrum": 42161, "optimism": 10, "bsc": 56, "base": 8453, "mantle": 5000}
        chain_id = chain_id_map.get(request.chain, 1)
        return [
            make_step(
                index=1, action="deposit_lp",
                title="Pendle V2 native exec (pending IDL wire-up)",
                description=(
                    "Pendle V2 router calldata encoder is staged but the "
                    "3-mode selector overloads need PendleSDK alignment. "
                    "Until then, finalise the position on app.pendle.fi — "
                    "all amount/range data flows through the same Preview "
                    "card."
                ),
                chain=request.chain, wallet="MetaMask", protocol="pendle-v2",
                asset_in=request.asset_in, amount_in=str(request.amount_in),
                slippage_bps=request.slippage_bps,
                blocker_codes=["POOL_LINK_REDIRECT"],
            ),
        ]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        return VerifyResult(
            confirmed=False,
            detail="Pendle V2 receipt verify: read SY/PT/YT balanceOf delta or LP shares.",
        )
